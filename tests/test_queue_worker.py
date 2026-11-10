import json
import os
from pathlib import Path
import tempfile
import unittest

from worker.queue_worker import Worker, WorkerBlocked, atomic_json, initialize, read_json, validate_job, ValidationError


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = initialize(Path(self.temp.name) / "jobs")
        (self.root / "inputs" / "sample.psd").write_bytes(b"fixture, not a real PSD")
        (self.root / "inputs" / "sample.aep").write_bytes(b"fixture, not a real AEP")

    def tearDown(self):
        self.temp.cleanup()

    def job(self, name="test-01", **changes):
        value = {"id": name, "action": "ps-export-png", "input": "inputs/sample.psd", "options": {}}
        value.update(changes)
        return value

    def enqueue(self, job, filename=None):
        path = self.root / "queue" / (filename or job["id"] + ".json")
        atomic_json(path, job)
        return path

    def run_once(self, job=None, **kwargs):
        if job is not None:
            self.enqueue(job)
        with Worker(self.root, **kwargs) as worker:
            return worker.drain()

    def test_simulation_never_claims_success_or_outputs(self):
        result = self.run_once(self.job(), simulate=True)[0]
        self.assertEqual(result["state"], "simulated")
        self.assertFalse(result["native_executed"])
        self.assertEqual(result["outputs"], [])
        self.assertEqual(list((self.root / "outputs").iterdir()), [])

    def test_native_outputs_are_verified(self):
        def fake(action, input_path, output_dir, options, config, log):
            self.assertEqual(action, "ps-export-png")
            target = output_dir / "export.png"
            target.write_bytes(b"not-real-png-test-fixture")
            return [target]
        result = self.run_once(self.job(), runner=fake)[0]
        self.assertEqual(result["state"], "succeeded")
        self.assertEqual(result["outputs"], ["outputs/test-01/export.png"])

    def test_empty_missing_external_outputs_fail(self):
        for index, kind in enumerate(("empty", "missing", "external", "none")):
            def fake(action, source, out, options, config, log):
                target = out / "out.png"
                if kind == "empty":
                    target.touch()
                if kind == "external":
                    target = source
                return [] if kind == "none" else [target]
            result = self.run_once(self.job(str(index)), runner=fake)[0]
            self.assertEqual(result["state"], "failed")

    def test_duplicate_preserves_terminal_status(self):
        self.run_once(self.job(), simulate=True)
        original = self.root / "status" / "test-01.json"
        before = original.read_bytes()
        result = self.run_once(self.job(), simulate=True)[0]
        self.assertEqual(result["state"], "duplicate")
        self.assertEqual(before, original.read_bytes())

    def test_lock_refuses_second_worker(self):
        with Worker(self.root):
            with self.assertRaises(WorkerBlocked):
                with Worker(self.root):
                    pass
        self.assertFalse((self.root / ".worker.lock").exists())

    def test_malformed_and_oversized_manifest(self):
        for name, data in (("broken", b"{bad"), ("huge", b" " * 65537)):
            (self.root / "queue" / (name + ".json")).write_bytes(data)
        results = self.run_once(simulate=True)
        self.assertEqual([item["state"] for item in results], ["rejected", "rejected"])

    def test_traversal_absolute_and_extra_fields_rejected(self):
        for index, value in enumerate(("../outside.psd", "inputs/../outside.psd", "/tmp/file.psd", "C:/tmp/file.psd", "inputs\\sample.psd")):
            self.assertEqual(self.run_once(self.job(str(index), input=value), simulate=True)[0]["state"], "rejected")
        self.assertEqual(self.run_once(self.job("extra", command="evil"), simulate=True)[0]["state"], "rejected")

    def test_filename_id_must_match(self):
        self.enqueue(self.job(), "other.json")
        self.assertEqual(self.run_once(simulate=True)[0]["state"], "rejected")
        self.assertFalse((self.root / "status" / "test-01.json").exists())

    def test_symlink_escape_rejected(self):
        target = Path(self.temp.name) / "outside.psd"
        target.write_bytes(b"outside")
        try:
            (self.root / "inputs" / "link.psd").symlink_to(target)
        except OSError:
            self.skipTest("Symlinks unavailable")
        result = self.run_once(self.job(input="inputs/link.psd"), simulate=True)[0]
        self.assertEqual(result["state"], "rejected")

    def test_manifest_symlink_rejected(self):
        target = Path(self.temp.name) / "manifest.json"
        atomic_json(target, self.job())
        try:
            (self.root / "queue" / "test-01.json").symlink_to(target)
        except OSError:
            self.skipTest("Symlinks unavailable")
        self.assertEqual(self.run_once(simulate=True)[0]["state"], "rejected")
        self.assertTrue(target.is_file())

    def test_adapter_failure_continues_serial_queue(self):
        def fake(*_):
            raise RuntimeError("Example Adobe failure")
        self.enqueue(self.job("second"))
        result = self.run_once(self.job("first"), runner=fake)
        self.assertEqual([item["state"] for item in result], ["failed", "failed"])

    def test_timeout_blocks_all_later_jobs(self):
        class TimeoutMayStillRun(RuntimeError):
            pass
        def fake(*_):
            raise TimeoutMayStillRun("Host may still be working")
        self.enqueue(self.job("b"))
        with self.assertRaises(WorkerBlocked):
            self.run_once(self.job("a"), runner=fake)
        self.assertEqual(read_json(self.root / "status" / "a.json")["state"], "unknown")
        self.assertTrue((self.root / "queue" / "b.json").exists())
        self.assertTrue((self.root / "blocked.json").exists())
        with self.assertRaises(WorkerBlocked):
            with Worker(self.root):
                pass

    def test_interrupt_blocks_uncertain_native_execution(self):
        def fake(*_):
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self.run_once(self.job(), runner=fake)
        self.assertEqual(read_json(self.root / "status" / "test-01.json")["state"], "unknown")
        self.assertTrue((self.root / "blocked.json").exists())

    def test_crash_claim_does_not_retry(self):
        atomic_json(self.root / "processing" / "test-01.json", self.job())
        with self.assertRaises(WorkerBlocked):
            with Worker(self.root):
                pass
        self.assertEqual(read_json(self.root / "status" / "test-01.json")["state"], "unknown")

    def test_reviewed_orphan_recovery_allows_fresh_jobs(self):
        atomic_json(self.root / "processing" / "test-01.json", self.job())
        with self.assertRaises(WorkerBlocked):
            with Worker(self.root):
                pass
        self.assertEqual(list((self.root / "processing").iterdir()), [])
        self.assertEqual(len(list((self.root / "archive").iterdir())), 1)
        # Represents the operator confirming Adobe is idle and reviewing evidence.
        (self.root / "blocked.json").unlink()
        result = self.run_once(self.job("fresh-id"), simulate=True)[0]
        self.assertEqual(result["state"], "simulated")
        self.assertEqual(read_json(self.root / "status" / "test-01.json")["state"], "unknown")

    def test_ae_options_and_frame_range(self):
        job = self.job(action="ae-render", input="inputs/sample.aep", options={"comp": "Main", "output_name": "frame_[####].png", "start_frame": -5, "end_frame": 20})
        validate_job(job, "test-01.json", self.root)
        for options in ({"comp": "Main", "output_name": "../escape.mov"}, {"comp": "Main", "output_name": "frame.png"}, {"comp": "Main", "output_name": "out.mov", "start_frame": True}, {"comp": "Main", "output_name": "out.mov", "start_frame": 2, "end_frame": 1}):
            with self.assertRaises(ValidationError):
                validate_job(dict(job, options=options), "test-01.json", self.root)

    def test_existing_output_is_not_overwritten(self):
        (self.root / "outputs" / "test-01").mkdir()
        result = self.run_once(self.job(), runner=lambda *_: [])[0]
        self.assertEqual(result["state"], "rejected")

    def test_invalid_output_filenames_rejected_during_simulation(self):
        for name in ('CON.mov', 'quote".mov', 'two_[##]_[##].png', 'frame_[####].mov', 'bad_[####]#.png'):
            job = self.job(action="ae-render", input="inputs/sample.aep", options={"comp": "Main", "output_name": name})
            with self.assertRaises(ValidationError, msg=name):
                validate_job(job, "test-01.json", self.root)

    def test_reserved_job_ids_rejected_and_map_to_safe_status_names(self):
        for name in ("CON", "aux", "NuL", "PRN", "com1", "LPT9"):
            with self.assertRaises(ValidationError):
                validate_job(self.job(name), name + ".json", self.root)
            self.assertTrue(Worker.file_id(Path(name + ".json")).startswith("invalid-"))

    @unittest.skipIf(os.name == "nt", "Windows itself cannot create reserved queue filenames")
    def test_reserved_manifest_filename_is_recorded_under_safe_hash(self):
        self.enqueue(self.job("CON"))
        result = self.run_once(simulate=True)[0]
        self.assertEqual(result["state"], "rejected")
        self.assertTrue(result["id"].startswith("invalid-"))
        self.assertTrue((self.root / "status" / (result["id"] + ".json")).is_file())


if __name__ == "__main__":
    unittest.main()
