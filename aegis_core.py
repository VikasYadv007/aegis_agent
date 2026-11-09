"""Windows file operations with durable recovery and no overwrite semantics."""

import json
import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path


def data_dir():
    path = Path(
        os.environ.get("AEGIS_DATA_DIR")
        or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Aegis"
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_json(path, default):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value if isinstance(value, type(default)) else default
    except (OSError, ValueError):
        return default


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".aegis-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def validate_folder(name):
    if (
        not name
        or name in {".", ".."}
        or len(name) > 100
        or name.endswith((".", " "))
        or re.search(r'[<>:"/\\|?*\x00-\x1f]', name)
        or re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", name)
    ):
        raise ValueError(
            "Use a single valid Windows folder name (maximum 100 characters)."
        )
    return name


def fingerprint(path):
    stat = Path(path).stat()
    return [stat.st_size, stat.st_mtime_ns, stat.st_ino]


def safe_move(source, destination):
    """Same-volume Windows rename preserves file metadata and refuses collisions."""
    source, destination = Path(source), Path(destination)
    if destination.exists():
        raise FileExistsError(f"Destination already exists: {destination.name}")
    if source.is_symlink() or destination.parent.is_symlink():
        raise ValueError("Symbolic links cannot be organized.")
    if os.name != "nt":
        raise OSError("This file mover requires Windows no-overwrite rename semantics.")
    os.rename(source, destination)


JOURNAL = ".aegis-undo.jsonl"
EXCLUDED = {
    "aegis_config.json",
    "aegis_history.json",
    "aegis_undo_log.json",
    "agent_undo_log.json",
}


def eligible(path, exclusions):
    return (
        path.is_file()
        and not path.is_symlink()
        and not path.name.startswith(".")
        and path.name.lower() not in EXCLUDED | exclusions
        and path.suffix.lower() not in exclusions
        and path.resolve() != Path(sys.executable).resolve()
        and path.suffix.lower() not in {".crdownload", ".part", ".download"}
    )


def append_record(stream, record):
    stream.write(json.dumps(record) + "\n")
    stream.flush()
    os.fsync(stream.fileno())


def execute_plan(root, plan, progress=None, cancel=None):
    root = Path(root).resolve()
    plan = [
        item
        for item in plan
        if item["status"] == "Will Move" and item.get("included", True)
    ]
    if not plan or (cancel and cancel.is_set()):
        return 0, []
    # Validate all destinations before touching any user files.
    for item in plan:
        validate_folder(item["dest_folder"])
        src = item["record"].path
        dest_dir = root / item["dest_folder"]
        if src.parent.resolve() != root or dest_dir.resolve().parent != root:
            raise ValueError("A destination escapes the selected folder.")
    journal = root / JOURNAL
    if journal.exists():
        archive = root / ".aegis-history"
        archive.mkdir(exist_ok=True)
        journal.rename(
            archive / (datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".jsonl")
        )
    moved, errors = 0, []
    with journal.open("x", encoding="utf-8") as stream:
        for index, item in enumerate(plan):
            if cancel and cancel.is_set():
                break
            src = item["record"].path
            dest = root / item["dest_folder"] / src.name
            try:
                if fingerprint(src) != item["record"].identity:
                    raise ValueError("File changed since preview; analyze again")
                dest.parent.mkdir(exist_ok=True)
                if dest.parent.resolve().parent != root or dest.exists():
                    raise FileExistsError(
                        "Destination exists or points outside the target"
                    )
                record = {
                    "original": str(src),
                    "new": str(dest),
                    "identity": fingerprint(src),
                }
                # Persist intent BEFORE rename so interruption never loses the recovery path.
                append_record(stream, record)
                safe_move(src, dest)
                item["status"] = "Moved"
                moved += 1
            except (OSError, ValueError) as exc:
                item["status"] = "Skipped"
                item["error"] = str(exc)
                errors.append(f"{src.name}: {exc}")
            if progress:
                progress(index + 1, len(plan), src.name)
    return moved, errors


def undo(root, journal_path=None, progress=None, cancel=None):
    root = Path(root).resolve()
    journal = Path(journal_path).resolve() if journal_path else root / JOURNAL
    allowed = {root, root / ".aegis-history"}
    if journal.parent not in allowed or journal.is_symlink():
        raise ValueError("Recovery journal must belong to the selected folder.")
    records = []
    lines = journal.read_text(encoding="utf-8").splitlines(keepends=True)
    for index, line in enumerate(lines):
        try:
            records.append(json.loads(line))
        except ValueError:
            # An interrupted final append cannot have reached its subsequent rename.
            if index == len(lines) - 1 and not line.endswith("\n"):
                break
            raise ValueError("Recovery journal is damaged; no files were restored.")
    # Validate the complete journal before making any changes.
    for item in records:
        if not isinstance(item, dict) or not all(
            key in item for key in ("original", "new", "identity")
        ):
            raise ValueError("Recovery journal contains an invalid record.")
        if not isinstance(item["identity"], list) or len(item["identity"]) != 3:
            raise ValueError("Recovery journal contains an invalid file identity.")
    restored, errors, stopped = 0, [], False
    for index, item in enumerate(reversed(records)):
        if cancel and cancel.is_set():
            stopped = True
            break
        src, dest = Path(item["new"]), Path(item["original"])
        try:
            if dest.parent.resolve() != root or src.parent.resolve().parent != root:
                raise ValueError("Undo path escapes the selected folder")
            if (
                not src.exists()
                and dest.exists()
                and fingerprint(dest) == item["identity"]
            ):
                continue  # Intent that did not move, or already restored in a prior attempt.
            if fingerprint(src) != item["identity"]:
                raise ValueError("Organized file changed; left untouched")
            safe_move(src, dest)
            restored += 1
            try:
                src.parent.rmdir()  # Only succeeds for empty folders.
            except OSError:
                pass
        except (OSError, ValueError) as exc:
            errors.append(f"{dest.name}: {exc}")
        finally:
            if progress:
                progress(index + 1, len(records), dest.name)
    if not errors and not stopped:
        journal.unlink()
    return restored, errors


def recovery_sessions(root):
    """Newest first; only journals physically inside this target are listed."""
    root = Path(root).resolve()
    paths = []
    if (root / JOURNAL).is_file():
        paths.append(root / JOURNAL)
    archive = root / ".aegis-history"
    if (
        archive.is_dir()
        and not archive.is_symlink()
        and archive.resolve().parent == root
    ):
        paths.extend(sorted(archive.glob("*.jsonl"), reverse=True))
    return [path for path in paths if not path.is_symlink()]
