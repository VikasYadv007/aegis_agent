import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from aegis_analysis import analyze, AnalysisCancelled, calculate_file_hash
from aegis_core import execute_plan, undo, recovery_sessions, JOURNAL


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def file(self, name, content=b"sample"):
        path = self.root / name
        path.write_bytes(content)
        return path

    def test_type_mode_and_exclusions(self):
        self.file("notes.pdf")
        self.file("photo.png", b"image")
        self.file("ignore.tmp")
        self.file("incomplete.crdownload")
        plan, warnings = analyze(self.root, strategy="File type", exclusions=".tmp")
        self.assertEqual({p["dest_folder"] for p in plan}, {"Documents", "Images"})
        self.assertEqual(warnings, [])
        self.assertTrue((self.root / "notes.pdf").exists())

    def test_month_uses_modification_time(self):
        file = self.file("notes.txt")
        from datetime import datetime

        stamp = datetime(2024, 3, 12).timestamp()
        os.utime(file, (stamp, stamp))
        plan, _ = analyze(self.root, strategy="By month")
        self.assertEqual(plan[0]["dest_folder"], "2024-03")

    def test_identical_size_is_not_duplicate_evidence(self):
        self.file("a.txt", b"abc")
        self.file("b.txt", b"xyz")
        self.file("copy.txt", b"abc")
        plan, _ = analyze(self.root)
        self.assertEqual(sum(p["duplicate"] for p in plan), 1)

    def test_unreadable_hashes_are_not_duplicates(self):
        self.file("a.txt")
        self.file("b.txt")
        with patch("aegis_analysis.calculate_file_hash", return_value=None):
            plan, warnings = analyze(self.root)
        self.assertEqual(sum(p["duplicate"] for p in plan), 0)
        self.assertEqual(len(warnings), 2)

    def test_conflicts_visible_before_execution(self):
        self.file("notes.txt")
        (self.root / "Documents").mkdir()
        (self.root / "Documents" / "notes.txt").write_text("existing")
        plan, _ = analyze(self.root, strategy="File type")
        self.assertEqual(plan[0]["status"], "Conflict")
        self.assertFalse(plan[0]["included"])

    def test_no_recursion(self):
        folder = self.root / "subfolder"
        folder.mkdir()
        (folder / "nested.txt").write_text("untouched")
        self.assertEqual(analyze(self.root)[0], [])

    def test_cancel_before_analysis_and_during_hash(self):
        path = self.file("large.txt")
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(AnalysisCancelled):
            analyze(self.root, cancel=cancel)
        with self.assertRaises(AnalysisCancelled):
            calculate_file_hash(path, cancel=cancel)

    def test_deterministic_plans(self):
        for index in range(20):
            self.file(f"project {index}.txt", str(index).encode())
        a, _ = analyze(self.root)
        b, _ = analyze(self.root)
        self.assertEqual(
            [(p["record"].name, p["dest_folder"]) for p in a],
            [(p["record"].name, p["dest_folder"]) for p in b],
        )

    def test_long_download_stream_is_split_into_distinct_sessions(self):
        import time

        start = time.time()
        for index in range(40):
            path = self.file(f"project {index}.txt", str(index).encode())
            os.utime(path, (start + index * 240, start + index * 240))
        plan, _ = analyze(self.root, duplicates=False)
        self.assertGreaterEqual(len({p["dest_folder"] for p in plan}), 3)

    @unittest.skipUnless(os.name == "nt", "Windows move semantics")
    def test_cancel_moves_keeps_recoverable_partial_run(self):
        for index in range(5):
            self.file(f"file{index}.txt", str(index).encode())
        plan, _ = analyze(self.root, strategy="File type")
        cancel = threading.Event()
        count, errors = execute_plan(
            self.root, plan, progress=lambda *args: cancel.set(), cancel=cancel
        )
        self.assertEqual((count, errors), (1, []))
        self.assertEqual(undo(self.root), (1, []))
        self.assertEqual(len(list(self.root.glob("*.txt"))), 5)

    @unittest.skipUnless(os.name == "nt", "Windows move semantics")
    def test_excluded_plan_does_not_replace_recovery(self):
        self.file("a.txt")
        plan, _ = analyze(self.root, strategy="File type")
        execute_plan(self.root, plan)
        previous = (self.root / JOURNAL).read_bytes()
        self.file("b.txt", b"next")
        plan, _ = analyze(self.root, strategy="File type")
        plan[0]["included"] = False
        self.assertEqual(execute_plan(self.root, plan), (0, []))
        self.assertEqual((self.root / JOURNAL).read_bytes(), previous)

    @unittest.skipUnless(os.name == "nt", "Windows move semantics")
    def test_archived_session_can_be_restored(self):
        self.file("first.txt")
        execute_plan(self.root, analyze(self.root, strategy="File type")[0])
        self.file("second.txt", b"second")
        execute_plan(self.root, analyze(self.root, strategy="File type")[0])
        sessions = recovery_sessions(self.root)
        self.assertEqual(len(sessions), 2)
        self.assertEqual(undo(self.root, sessions[0]), (1, []))
        self.assertEqual(undo(self.root, sessions[1]), (1, []))
        self.assertTrue((self.root / "first.txt").exists())
        self.assertTrue((self.root / "second.txt").exists())

    def test_external_recovery_journal_is_rejected(self):
        with self.assertRaises(ValueError):
            undo(self.root, self.root.parent / "untrusted.jsonl")
