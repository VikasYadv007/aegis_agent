"""Opt-in packaged integration check, operating exclusively on temporary files."""

import importlib
import json
import os
from pathlib import Path
import tempfile
import time


def run(output):
    output = Path(output).resolve()
    with tempfile.TemporaryDirectory(prefix="aegis-smoke-") as temporary:
        root = Path(temporary)
        os.environ["AEGIS_DATA_DIR"] = str(root / "settings")
        target = root / "sample files"
        target.mkdir()
        samples = {
            "report alpha.txt": b"alpha",
            "report copy.txt": b"alpha",
            "report beta.txt": b"different beta",
            "unicode \u6587\u4ef6.txt": b"unicode",
        }
        for name, content in samples.items():
            (target / name).write_bytes(content)
        from aegis_core import data_dir, save_json

        save_json(data_dir() / "aegis_config.json", {"last_dir": str(target)})
        module = importlib.import_module("aegis_app")
        from google import genai
        from google.genai import types

        with genai.Client(
            api_key="smoke-test-no-network",
            http_options=types.HttpOptions(timeout=30000),
        ) as client:
            assert client.models is not None
        dialogs = []
        module.messagebox.askyesno = lambda *a, **k: True
        module.messagebox.showinfo = lambda *a, **k: dialogs.append(a)
        module.messagebox.showwarning = lambda *a, **k: dialogs.append(a)
        module.messagebox.showerror = lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError(str(a))
        )
        app = module.AegisAgentApp()
        app.withdraw()
        failures = []
        app.report_callback_exception = lambda *args: failures.append(str(args[1]))

        def wait():
            deadline = time.monotonic() + 30
            while app.busy and time.monotonic() < deadline:
                app.update()
                time.sleep(0.02)
            app.update()
            assert not app.busy, "Worker timed out"
            assert not failures, failures

        try:
            app.run_analysis()
            wait()
            assert len(app.organization_plan) == len(samples)
            assert any(
                i["dest_folder"] == "Review - Duplicates" for i in app.organization_plan
            )
            assert all(
                (target / name).exists() for name in samples
            ), "Preview moved files"
            app.filter.set("Duplicates")
            app.render_plan()
            assert len(app.visible_indices) == 1
            app.clear_filters()
            app.tree.selection_set("0")
            app.toggle_selected()
            assert not app.organization_plan[0]["included"]
            app.toggle_selected()
            assert app.organization_plan[0]["included"]
            app.dest_entry.delete(0, "end")
            app.dest_entry.insert(0, "Custom folder")
            app.update_file_destination()
            assert app.organization_plan[0]["dest_folder"] == "Custom folder"
            app.export_plan(root / "report.csv")
            assert (root / "report.csv").exists()
            app.run_execution()
            wait()
            assert all(
                not (target / name).exists() for name in samples
            ), "Execution failed"
            app.run_undo()
            wait()
            assert all(
                (target / name).read_bytes() == content
                for name, content in samples.items()
            )
            for view in app.views:
                app.switch_view(view)
                app.update()
            for theme in ["Dark", "Light"]:
                app.change_theme(theme)
                app.update()
            app.strategy.set("File type")
            app.run_analysis()
            wait()
            assert any(
                item["dest_folder"] == "Documents" for item in app.organization_plan
            )
            # A large preview renders a bounded page instead of thousands of widgets.
            original = app.organization_plan
            app.organization_plan = [dict(original[0]) for _ in range(601)]
            app.render_plan()
            assert len(app.tree.get_children()) == app.PAGE_SIZE
            app.change_page(1)
            assert app.page == 1
            app.change_page(1)
            assert len(app.tree.get_children()) == 101
            app.organization_plan = original
            app.reset_page()
            output.write_text(
                json.dumps(
                    {
                        "passed": True,
                        "files": len(samples),
                        "checks": [
                            "startup",
                            "all views",
                            "preview",
                            "duplicates",
                            "filters",
                            "include/exclude",
                            "destination edit",
                            "CSV export",
                            "execute",
                            "undo",
                            "unicode paths",
                            "light/dark themes",
                            "file-type mode",
                            "601-row pagination",
                        ],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        finally:
            app.destroy()
