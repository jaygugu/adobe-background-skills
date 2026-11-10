"""Native Adobe adapters; no Adobe installation is bundled with this project.

This baseline supports rendering one AE composition and exporting a PSD/PSB
composite to PNG. It does not reconstruct the owner's earlier custom scripts.
Run on the workstation that has licensed Adobe applications installed.
"""

from __future__ import annotations

import json
import platform
import re
import subprocess
from pathlib import Path


class TimeoutMayStillRun(RuntimeError):
    """A native Adobe task may still be active; stop the queue for review."""


_AE_OPTIONS = {
    "comp", "output_name", "output_module", "render_settings",
    "start_frame", "end_frame",
}
_MOVIE_SUFFIXES = {".mov", ".avi", ".mp4"}
_SEQUENCE_SUFFIXES = {".png", ".jpg", ".jpeg", ".exr", ".tif", ".tiff"}
_CONTROL = ".control"


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 512:
        raise ValueError(f"{label} must be a nonempty string of at most 512 characters")
    if any(ord(char) < 32 for char in value):
        raise ValueError(f"{label} must not contain control characters")
    return value


def _timeout(config: dict) -> int:
    value = config.get("timeout_seconds", 3600)
    if type(value) is not int or not 1 <= value <= 86400:
        raise ValueError("timeout_seconds must be an integer from 1 to 86400")
    return value


def _output_name(value: object) -> str:
    value = _text(value, "output_name")
    if any(char in value for char in '/\\:*?"<>|') or value in {".", ".."}:
        raise ValueError("output_name must be a filename, not a path")
    if value.endswith((".", " ")):
        raise ValueError("output_name must not end in a dot or space")
    stem = value.split(".", 1)[0].upper()
    if stem in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)],
                *[f"LPT{i}" for i in range(1, 10)]}:
        raise ValueError("output_name is a reserved Windows filename")
    suffix = Path(value).suffix.lower()
    matches = re.findall(r"\[(#+)\]", value)
    if suffix in _MOVIE_SUFFIXES:
        if "[" in value or "]" in value or "#" in value:
            raise ValueError("movie output_name cannot contain a frame pattern")
    elif suffix in _SEQUENCE_SUFFIXES:
        if len(matches) != 1 or not 1 <= len(matches[0]) <= 12:
            raise ValueError("image output_name requires one [####] frame pattern")
        stripped = re.sub(r"\[#+\]", "", value)
        if any(char in stripped for char in "[]#"):
            raise ValueError("invalid frame pattern")
    else:
        raise ValueError("unsupported render output extension")
    return value


def _ae_command(input_path: Path, output_dir: Path, options: dict, config: dict) -> list[str]:
    if not isinstance(options, dict) or options.keys() - _AE_OPTIONS:
        raise ValueError("unsupported ae-render options")
    if input_path.suffix.lower() not in {".aep", ".aepx"}:
        raise ValueError("ae-render requires an .aep or .aepx input")
    executable = Path(_text(config.get("aerender"), "aerender"))
    if not executable.is_absolute() or not executable.is_file():
        raise ValueError("aerender must name an existing absolute executable path")
    command = [str(executable), "-project", str(input_path),
               "-comp", _text(options.get("comp"), "comp"),
               "-output", str(output_dir / _output_name(options.get("output_name"))),
               "-close", "DO_NOT_SAVE_CHANGES"]
    for option, flag in (("output_module", "-OMtemplate"),
                         ("render_settings", "-RStemplate")):
        if option in options:
            command += [flag, _text(options[option], option)]
    for option, flag in (("start_frame", "-s"), ("end_frame", "-e")):
        if option in options:
            if type(options[option]) is not int:
                raise ValueError(f"{option} must be an integer")
            command += [flag, str(options[option])]
    if "start_frame" in options and "end_frame" in options:
        if options["end_frame"] < options["start_frame"]:
            raise ValueError("end_frame must be at least start_frame (inclusive)")
    return command


def _launch(command: list[str], timeout: int, log_path: Path) -> int:
    # Keep arguments out of shell interpretation, including spaces and quotes.
    # subprocess.run terminates its direct child on timeout. Adobe itself may
    # still be processing, especially when invoked through COM/Apple events.
    with log_path.open("a", encoding="utf-8") as log:
        log.write("Adapter command (argument array): " + json.dumps(command) + "\n")
        log.flush()
        try:
            process = subprocess.run(
                command, stdin=subprocess.DEVNULL, stdout=log,
                stderr=subprocess.STDOUT, shell=False, timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutMayStillRun(
                "Adobe timed out; it may still be running. Inspect the app and "
                "output folder before manually clearing the queue block."
            ) from exc
    return process.returncode


def _rendered_files(output_dir: Path, name: str, *, expected_frames: int | None = None) -> list[Path]:
    match = re.search(r"\[(#+)\]", name)
    if match:
        expression = (re.escape(name[:match.start()]) + r"(-?\d{" +
                      str(len(match.group(1))) + r",})" + re.escape(name[match.end():]))
        result = sorted(path for path in output_dir.iterdir()
                        if re.fullmatch(expression, path.name))
    else:
        result = [output_dir / name]
    if not result or any(path.is_symlink() or not path.is_file() or path.stat().st_size == 0
                         for path in result):
        raise RuntimeError("Adobe reported completion but no nonempty expected output was found")
    if match:
        # AE output numbering may have a project/template offset. Verify count
        # and continuity, not equality to the requested timeline start frame.
        numbers = sorted(int(re.fullmatch(expression, path.name).group(1)) for path in result)
        if any(current != previous + 1 for previous, current in zip(numbers, numbers[1:])):
            raise RuntimeError("Rendered sequence has missing or duplicate frame numbers")
        if expected_frames is not None and len(numbers) != expected_frames:
            raise RuntimeError(
                f"Rendered sequence contains {len(numbers)} frames; expected {expected_frames} "
                "for the inclusive requested range"
            )
    return result


def _photoshop_command(control: Path, jsx: Path, config: dict, system: str) -> list[str]:
    if system == "Windows":
        launcher = control / "launch.ps1"
        launcher.write_text(
            'param([Parameter(Mandatory=$true)][string]$JsxPath)\n'
            "$ErrorActionPreference = 'Stop'\n"
            "$app = New-Object -ComObject Photoshop.Application\n"
            "$result = $app.DoJavaScriptFile($JsxPath)\n"
            "[Console]::Out.WriteLine([string]$result)\n",
            encoding="utf-8",
        )
        # Use the system's policy. Do not silently bypass execution restrictions.
        return ["powershell.exe", "-NoProfile", "-NonInteractive", "-File",
                str(launcher), "-JsxPath", str(jsx)]
    app = config.get("photoshop_app_name", "Adobe Photoshop 2026")
    if not isinstance(app, str) or not re.fullmatch(r"Adobe Photoshop(?: [A-Za-z0-9 ._-]+)?", app):
        raise ValueError("photoshop_app_name must be the installed Adobe Photoshop app name")
    launcher = control / "launch.applescript"
    launcher.write_text(
        "on run argv\n"
        "  set scriptPath to item 1 of argv\n"
        f"  with timeout of {_timeout(config)} seconds\n"
        f'    tell application "{app}"\n'
        "      do javascript file (POSIX file scriptPath)\n"
        "    end tell\n"
        "  end timeout\n"
        "end run\n",
        encoding="utf-8",
    )
    return ["/usr/bin/osascript", str(launcher), str(jsx)]


def run(action: str, input_path: Path, output_dir: Path, options: dict,
        config: dict, log_path: Path) -> list[Path]:
    """Execute one job; caller owns locking and a fresh output folder.

    AE precondition: prepare a project copy with an empty Render Queue. The
    adapter cannot inspect native AEP internals: an existing queue item can
    contain extra output modules whose stored paths are not all overridden by
    -output. Never claim output-path confinement without this preflight.
    """
    system = platform.system()
    if system not in {"Windows", "Darwin"}:
        raise RuntimeError("Native Adobe jobs require Windows or macOS; use --simulate elsewhere")
    input_path = Path(input_path).resolve(strict=True)
    output_dir = Path(output_dir)
    log_path = Path(log_path)
    if not input_path.is_file():
        raise ValueError("input must be a regular file")
    if output_dir.is_symlink() or not output_dir.is_dir() or any(output_dir.iterdir()):
        raise ValueError("output_dir must be an empty, nonsymlink directory")
    timeout = _timeout(config)
    if action == "ae-render":
        command = _ae_command(input_path, output_dir, options, config)
        code = _launch(command, timeout, log_path)
        if code != 0:
            raise RuntimeError(f"aerender exited with code {code}; inspect the log")
        expected_frames = None
        if "start_frame" in options and "end_frame" in options:
            expected_frames = options["end_frame"] - options["start_frame"] + 1
        return _rendered_files(output_dir, options["output_name"], expected_frames=expected_frames)
    if action != "ps-export-png":
        raise ValueError(f"unsupported action: {action}")
    if options != {}:
        raise ValueError("ps-export-png accepts no options in this baseline")
    if input_path.suffix.lower() not in {".psd", ".psb"}:
        raise ValueError("ps-export-png requires a .psd or .psb input")
    control = output_dir / _CONTROL
    control.mkdir()
    output = output_dir / "export.png"
    marker = control / "completion.txt"
    jsx = control / "run.jsx"
    payload = {"input": str(input_path), "output": str(output), "marker": str(marker)}
    source = Path(__file__).with_name("photoshop_export.jsx").read_text(encoding="utf-8")
    jsx.write_text("var ADOBE_JOB = " + json.dumps(payload, ensure_ascii=True) + ";\n" + source,
                   encoding="utf-8")
    command = _photoshop_command(control, jsx, config, system)
    code = _launch(command, timeout, log_path)
    if not marker.is_file():
        # COM/Apple Events may fail after Adobe accepted the script. Without a
        # final marker, starting another job could overlap an active operation.
        raise TimeoutMayStillRun(
            f"Photoshop bridge exited with code {code} without a completion marker. "
            "Execution state is unknown; inspect Photoshop and the log before continuing."
        )
    result = marker.read_text(encoding="utf-8-sig")
    if result != "OK\n":
        raise RuntimeError("Photoshop export failed: " + result.removeprefix("ERROR\n").strip())
    if code != 0:
        raise RuntimeError(f"Photoshop bridge exited with code {code}; inspect the log")
    return _rendered_files(output_dir, "export.png")
