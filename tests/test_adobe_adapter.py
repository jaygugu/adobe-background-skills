import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "worker"))
import adobe_adapter as adapter


class AdobeAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="adobe adapter ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / 'Source Bình $name.aep'
        self.project.write_bytes(b"test-only fixture")
        self.output = self.root / "output"
        self.output.mkdir()
        self.log = self.root / "job.log"
        self.executable = self.root / "aerender test"
        self.executable.write_bytes(b"not executable: mocked")
        self.config = {"aerender": str(self.executable), "timeout_seconds": 30}

    def test_arguments_keep_unicode_spaces_and_metacharacters_literal(self):
        command = adapter._ae_command(self.project, self.output, {
            "comp": 'Master "Main"; $name', "output_name": "Final export.mov",
            "output_module": "Custom ProRes", "start_frame": 2, "end_frame": 10,
        }, self.config)
        self.assertEqual(command[command.index("-project") + 1], str(self.project))
        self.assertEqual(command[command.index("-comp") + 1], 'Master "Main"; $name')
        self.assertEqual(command[command.index("-output") + 1], str(self.output / "Final export.mov"))
        self.assertNotIn("-reuse", command)
        self.assertNotIn("-continueOnMissingFootage", command)
        self.assertIn("DO_NOT_SAVE_CHANGES", command)

    def test_rejects_paths_reserved_names_and_non_output_formats(self):
        for name in ["../bad.mov", "C:\\bad.mov", "/bad.mov", "file.aep", "CON.mov", "out.mov.", "frame.png"]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                adapter._output_name(name)

    def test_rejects_unknown_options_and_reversed_or_boolean_frames(self):
        for extra in [{"shell": "whoami"}, {"start_frame": True},
                      {"start_frame": 10, "end_frame": 9}]:
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                adapter._ae_command(self.project, self.output,
                                    {"comp": "Master", "output_name": "out.mov", **extra}, self.config)

    def test_sequence_outputs_match_only_nonempty_expected_files(self):
        (self.output / "frame_0001.png").write_bytes(b"one")
        (self.output / "frame_0002.png").write_bytes(b"two")
        (self.output / "other_0001.png").write_bytes(b"unrelated")
        self.assertEqual(len(adapter._rendered_files(self.output, "frame_[####].png")), 2)
        with self.assertRaises(RuntimeError):
            adapter._rendered_files(self.output, "absent.mov")

    def test_sequence_missing_trailing_frames_fails_requested_count(self):
        (self.output / "frame_0000.png").write_bytes(b"one")
        with self.assertRaisesRegex(RuntimeError, "expected 30"):
            adapter._rendered_files(self.output, "frame_[####].png", expected_frames=30)

    def test_sequence_gap_fails_even_without_requested_count(self):
        (self.output / "frame_0001.png").write_bytes(b"one")
        (self.output / "frame_0003.png").write_bytes(b"three")
        with self.assertRaisesRegex(RuntimeError, "missing or duplicate"):
            adapter._rendered_files(self.output, "frame_[####].png")

    def test_sequence_count_accepts_project_numbering_offset(self):
        for number in [1001, 1002, 1003]:
            (self.output / f"frame_{number}.png").write_bytes(b"frame")
        self.assertEqual(len(adapter._rendered_files(
            self.output, "frame_[####].png", expected_frames=3)), 3)

    def test_sequence_duplicate_number_with_different_padding_fails(self):
        (self.output / "frame_0001.png").write_bytes(b"one")
        (self.output / "frame_00001.png").write_bytes(b"also one")
        with self.assertRaisesRegex(RuntimeError, "missing or duplicate"):
            adapter._rendered_files(self.output, "frame_[####].png")

    def test_native_sequence_job_verifies_explicit_range(self):
        def incomplete_host(*args):
            (self.output / "frame_0000.png").write_bytes(b"one")
            return 0
        with patch.object(adapter.platform, "system", return_value="Darwin"), \
             patch.object(adapter, "_launch", side_effect=incomplete_host):
            with self.assertRaisesRegex(RuntimeError, "expected 30"):
                adapter.run("ae-render", self.project, self.output,
                            {"comp": "Master", "output_name": "frame_[####].png",
                             "start_frame": 0, "end_frame": 29}, self.config, self.log)

    def test_process_launch_uses_argument_array_and_no_shell(self):
        with patch.object(adapter.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as launch:
            self.assertEqual(adapter._launch(["program", "a ; b"], 30, self.log), 0)
        self.assertEqual(launch.call_args.args[0], ["program", "a ; b"])
        self.assertFalse(launch.call_args.kwargs["shell"])
        self.assertEqual(launch.call_args.kwargs["timeout"], 30)

    def test_launch_really_records_process_output(self):
        code = adapter._launch([sys.executable, "-c", "print('adapter smoke check')"], 10, self.log)
        self.assertEqual(code, 0)
        self.assertIn("adapter smoke check", self.log.read_text())

    def test_timeout_is_unknown_not_ordinary_failed(self):
        with patch.object(adapter.subprocess, "run", side_effect=subprocess.TimeoutExpired(["adobe"], 30)):
            with self.assertRaises(adapter.TimeoutMayStillRun):
                adapter._launch(["adobe"], 30, self.log)

    def test_windows_bridge_passes_script_as_argument(self):
        control = self.output / ".control"
        control.mkdir()
        jsx = control / 'run $name.jsx'
        command = adapter._photoshop_command(control, jsx, self.config, "Windows")
        self.assertEqual(command[-1], str(jsx))
        script = (control / "launch.ps1").read_text()
        self.assertIn("DoJavaScriptFile($JsxPath)", script)
        self.assertNotIn(str(jsx), script)
        self.assertNotIn("Bypass", command)

    def test_macos_bridge_uses_argv_and_validates_app_name(self):
        control = self.output / ".control"
        control.mkdir()
        jsx = control / 'run "quoted".jsx'
        command = adapter._photoshop_command(control, jsx, self.config, "Darwin")
        self.assertEqual(command[-1], str(jsx))
        script = (control / "launch.applescript").read_text()
        self.assertIn("item 1 of argv", script)
        self.assertIn("with timeout of 30 seconds", script)
        self.assertNotIn(str(jsx), script)
        with self.assertRaises(ValueError):
            adapter._photoshop_command(control, jsx, {"photoshop_app_name": 'bad"\n'}, "Darwin")

    def test_photoshop_requires_marker_and_nonempty_output(self):
        psd = self.root / 'Input Bình.psd'
        psd.write_bytes(b"test fixture")
        with patch.object(adapter.platform, "system", return_value="Windows"), \
             patch.object(adapter, "_launch", return_value=0):
            with self.assertRaises(adapter.TimeoutMayStillRun):
                adapter.run("ps-export-png", psd, self.output, {}, self.config, self.log)

    def test_photoshop_success_requires_completed_marker(self):
        psd = self.root / 'Input Bình.psd'
        psd.write_bytes(b"test fixture")
        def fake_host(*args):
            (self.output / "export.png").write_bytes(b"nonempty synthetic fixture")
            (self.output / ".control/completion.txt").write_text("OK\n")
            return 0
        with patch.object(adapter.platform, "system", return_value="Windows"), \
             patch.object(adapter, "_launch", side_effect=fake_host):
            self.assertEqual(adapter.run("ps-export-png", psd, self.output, {}, self.config, self.log),
                             [self.output / "export.png"])
        generated = (self.output / ".control/run.jsx").read_text()
        payload = json.loads(generated.splitlines()[0].removeprefix("var ADOBE_JOB = ")[:-1])
        self.assertEqual(payload["input"], str(psd))
        self.assertIn("app.documents.length !== 0", generated)

    def test_nonzero_aerender_exit_cannot_succeed(self):
        with patch.object(adapter.platform, "system", return_value="Darwin"), \
             patch.object(adapter, "_launch", return_value=3):
            with self.assertRaisesRegex(RuntimeError, "code 3"):
                adapter.run("ae-render", self.project, self.output,
                            {"comp": "Master", "output_name": "result.mov"}, self.config, self.log)

    def test_native_linux_refuses_instead_of_faking_completion(self):
        with patch.object(adapter.platform, "system", return_value="Linux"):
            with self.assertRaisesRegex(RuntimeError, "require Windows or macOS"):
                adapter.run("ae-render", self.project, self.output, {}, self.config, self.log)

    def test_nonempty_output_dir_is_never_reused(self):
        (self.output / "keep.txt").write_text("keep")
        with patch.object(adapter.platform, "system", return_value="Darwin"):
            with self.assertRaises(ValueError):
                adapter.run("ae-render", self.project, self.output, {}, self.config, self.log)
        self.assertEqual((self.output / "keep.txt").read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
