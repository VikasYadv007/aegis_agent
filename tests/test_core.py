import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from aegis_core import (
    JOURNAL,
    execute_plan,
    fingerprint,
    load_json,
    save_json,
    safe_move,
    undo,
    validate_folder,
)


@unittest.skipUnless(os.name == "nt", "Windows file semantics")
class FileSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "document.txt"
        self.source.write_text("original", encoding="utf-8")

    def plan(self, name="Organized"):
        return [
            {
                "record": SimpleNamespace(
                    path=self.source, identity=fingerprint(self.source)
                ),
                "dest_folder": name,
                "status": "Will Move",
            }
        ]

    def test_move_undo_preserves_metadata_and_contents(self):
        identity = fingerprint(self.source)
        created = self.source.stat().st_birthtime_ns
        self.assertEqual(execute_plan(self.root, self.plan()), (1, []))
        self.assertEqual(undo(self.root), (1, []))
        self.assertEqual(fingerprint(self.source), identity)
        self.assertEqual(self.source.stat().st_birthtime_ns, created)
        self.assertEqual(self.source.read_text(), "original")

    def test_existing_destination_is_never_overwritten(self):
        folder = self.root / "Organized"
        folder.mkdir()
        (folder / self.source.name).write_text("keep me")
        moved, errors = execute_plan(self.root, self.plan())
        self.assertEqual(moved, 0)
        self.assertEqual(len(errors), 1)
        self.assertEqual((folder / self.source.name).read_text(), "keep me")
        self.assertTrue(self.source.exists())

    def test_changed_preview_file_is_skipped(self):
        plan = self.plan()
        self.source.write_text("modified after preview")
        self.assertEqual(execute_plan(self.root, plan)[0], 0)
        self.assertTrue(self.source.exists())

    def test_undo_collision_keeps_recovery_journal_for_retry(self):
        execute_plan(self.root, self.plan())
        self.source.write_text("new file")
        self.assertEqual(undo(self.root)[0], 0)
        self.assertTrue((self.root / JOURNAL).exists())
        self.assertEqual(self.source.read_text(), "new file")
        self.source.unlink()
        self.assertEqual(undo(self.root), (1, []))

    def test_modified_destination_is_not_restored(self):
        execute_plan(self.root, self.plan())
        (self.root / "Organized" / self.source.name).write_text("edited")
        self.assertEqual(undo(self.root)[0], 0)
        self.assertTrue((self.root / JOURNAL).exists())

    def test_recover_after_interruption_between_intent_and_move(self):
        with patch(
            "aegis_core.safe_move", side_effect=OSError("simulated interruption")
        ):
            self.assertEqual(execute_plan(self.root, self.plan())[0], 0)
        self.assertEqual(undo(self.root), (0, []))
        self.assertEqual(self.source.read_text(), "original")

    def test_journal_is_durable_before_rename(self):
        def check(source, dest):
            lines = (self.root / JOURNAL).read_text().splitlines()
            self.assertEqual(json.loads(lines[-1])["original"], str(source))
            safe_move(source, dest)

        with patch("aegis_core.safe_move", side_effect=check):
            self.assertEqual(execute_plan(self.root, self.plan()), (1, []))

    def test_path_escape_is_rejected(self):
        for name in ["../escape", r"C:\escape", "NUL", "bad.", "a/b", "a:b", ".."]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                execute_plan(self.root, self.plan(name))
        self.assertTrue(self.source.exists())

    def test_atomic_config_replacement(self):
        path = self.root / "settings.json"
        save_json(path, {"a": 1})
        with patch("aegis_core.os.replace", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                save_json(path, {"a": 2})
        self.assertEqual(load_json(path, {}), {"a": 1})

    def test_previous_journal_is_archived(self):
        execute_plan(self.root, self.plan())
        self.source.write_text("another")
        execute_plan(self.root, self.plan("Other"))
        self.assertEqual(len(list((self.root / ".aegis-history").iterdir())), 1)
        self.assertEqual(undo(self.root), (1, []))

    def test_incomplete_final_journal_record_keeps_earlier_recovery(self):
        execute_plan(self.root, self.plan())
        with (self.root / JOURNAL).open("a") as stream:
            stream.write('{"original":')
        self.assertEqual(undo(self.root), (1, []))


if __name__ == "__main__":
    unittest.main()
