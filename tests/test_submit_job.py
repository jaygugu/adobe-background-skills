import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from worker.queue_worker import ValidationError, initialize, read_json
from worker.submit_job import submit


class SubmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = initialize(Path(self.temp.name) / "queue root")
        (self.root / "inputs" / "sample.psd").write_bytes(b"test fixture")
        self.job = {"id": "submit-1", "action": "ps-export-png", "input": "inputs/sample.psd", "options": {}}

    def tearDown(self):
        self.temp.cleanup()

    def test_publishes_valid_complete_json_without_temporary_files(self):
        target = submit(self.root, self.job)
        self.assertEqual(read_json(target), self.job)
        self.assertEqual(list((self.root / "queue").iterdir()), [target])

    def test_duplicate_does_not_overwrite(self):
        target = submit(self.root, self.job)
        content = target.read_bytes()
        with self.assertRaises(ValidationError):
            submit(self.root, self.job)
        self.assertEqual(target.read_bytes(), content)

    def test_status_processing_output_and_log_collisions_refused(self):
        for directory, filename in (("status", "submit-1.json"), ("processing", "submit-1.json"),
                                    ("outputs", "submit-1"), ("logs", "submit-1.log")):
            path = self.root / directory / filename
            path.write_text("keep me")
            with self.assertRaises(ValidationError):
                submit(self.root, self.job)
            self.assertEqual(path.read_text(), "keep me")
            path.unlink()

    def test_bad_job_and_missing_input_never_publish(self):
        for job in (dict(self.job, input="../bad.psd"), dict(self.job, input="inputs/missing.psd"), dict(self.job, id="../bad")):
            with self.assertRaises(ValidationError):
                submit(self.root, job)
        self.assertEqual(list((self.root / "queue").iterdir()), [])

    def test_reserved_windows_ids_never_publish(self):
        for name in ("CON", "aux", "NuL", "PRN", "com1", "LPT9"):
            with self.assertRaises(ValidationError):
                submit(self.root, dict(self.job, id=name))
        self.assertEqual(list((self.root / "queue").iterdir()), [])

    def test_unsupported_filesystem_cleans_temporary_file(self):
        with patch("worker.submit_job.os.link", side_effect=OSError("not supported")):
            with self.assertRaises(ValidationError):
                submit(self.root, self.job)
        self.assertEqual(list((self.root / "queue").iterdir()), [])

    def test_cli_submits_without_claiming_execution(self):
        manifest = Path(self.temp.name) / "source.json"
        manifest.write_text(json.dumps(self.job), encoding="utf-8")
        script = Path(__file__).resolve().parents[1] / "worker" / "submit_job.py"
        result = subprocess.run([sys.executable, str(script), "--root", str(self.root), "--job", str(manifest)],
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)["state"], "queued")
        self.assertFalse((self.root / "status" / "submit-1.json").exists())


if __name__ == "__main__":
    unittest.main()
