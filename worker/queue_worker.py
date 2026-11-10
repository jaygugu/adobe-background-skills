#!/usr/bin/env python3
"""Local, serial Adobe job queue. No Adobe software is required for --simulate."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import signal
import socket
import sys
import time
import uuid
from typing import Callable

MAX_MANIFEST_BYTES = 64 * 1024
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
WINDOWS_DEVICE_NAMES = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{n}" for prefix in ("COM", "LPT") for n in range(1, 10)
}
TERMINAL = {"succeeded", "failed", "rejected", "simulated", "unknown"}
DIRECTORIES = ("inputs", "queue", "processing", "status", "outputs", "logs", "archive", "rejected")


class ValidationError(ValueError):
    pass


class WorkerBlocked(RuntimeError):
    pass


def valid_job_id(value: object) -> bool:
    return (isinstance(value, str) and ID_PATTERN.fullmatch(value) is not None
            and value.upper() not in WINDOWS_DEVICE_NAMES)


def timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def atomic_json(path: Path, payload: dict) -> None:
    temp = path.with_name("." + path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temp.open("x", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def read_json(path: Path, limit: int = MAX_MANIFEST_BYTES) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValidationError("Expected a regular JSON file, not a symlink.")
    if path.stat().st_size > limit:
        raise ValidationError(f"JSON file exceeds {limit} bytes.")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValidationError(f"JSON file exceeds {limit} bytes.")
    try:
        value = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError("Invalid UTF-8 JSON: " + str(exc)) from exc
    if not isinstance(value, dict):
        raise ValidationError("JSON root must be an object.")
    return value


def initialize(root: Path) -> Path:
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    for name in DIRECTORIES:
        child = root / name
        if child.is_symlink():
            raise ValidationError(f"Queue directory cannot be a symlink: {name}")
        child.mkdir(exist_ok=True)
        if not child.is_dir() or child.resolve().parent != root:
            raise ValidationError(f"Invalid queue directory: {name}")
    return root


def safe_text(value: object, name: str, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValidationError(f"{name} must be a nonempty string, at most {maximum} characters.")
    if any(ord(char) < 32 for char in value):
        raise ValidationError(f"{name} contains a control character.")
    return value


def validate_job(job: dict, filename: str, root: Path) -> tuple[Path, dict]:
    if set(job) != {"id", "action", "input", "options"}:
        raise ValidationError("Job must contain exactly id, action, input and options.")
    job_id = job["id"]
    if not valid_job_id(job_id):
        raise ValidationError("Invalid job id; use 1–64 letters, digits, underscores or hyphens, excluding Windows device names such as CON or AUX.")
    if filename != job_id + ".json":
        raise ValidationError("Filename must equal the job id plus .json.")
    action = job["action"]
    if action not in ("ae-render", "ps-export-png"):
        raise ValidationError("Allowed actions: ae-render, ps-export-png.")
    source = safe_text(job["input"], "input", 4096)
    relative = PurePosixPath(source)
    if ("\\" in source or ":" in source or relative.is_absolute()
            or PureWindowsPath(source).is_absolute() or ".." in relative.parts
            or len(relative.parts) < 2 or relative.parts[0] != "inputs"):
        raise ValidationError("input must be a forward-slash path beneath inputs/, without traversal.")
    input_path = (root / source).resolve()
    if not input_path.is_relative_to(root / "inputs") or not input_path.is_file():
        raise ValidationError("Input file is missing or resolves outside inputs/.")
    options = job["options"]
    if not isinstance(options, dict):
        raise ValidationError("options must be an object.")
    if action == "ps-export-png":
        if options:
            raise ValidationError("ps-export-png currently accepts empty options only.")
        if input_path.suffix.lower() not in {".psd", ".psb"}:
            raise ValidationError("ps-export-png input must be .psd or .psb.")
    else:
        permitted = {"comp", "output_name", "output_module", "render_settings", "start_frame", "end_frame"}
        if set(options) - permitted or not {"comp", "output_name"}.issubset(options):
            raise ValidationError("ae-render requires comp/output_name and only documented options.")
        safe_text(options["comp"], "comp")
        output_name = safe_text(options["output_name"], "output_name")
        if any(char in output_name for char in '\\/:<>|?*"') or output_name in {".", ".."}:
            raise ValidationError("output_name must be a filename, without path separators.")
        if output_name.endswith((".", " ")):
            raise ValidationError("output_name cannot end in a dot or space.")
        if output_name.split(".")[0].upper() in WINDOWS_DEVICE_NAMES:
            raise ValidationError("output_name is a reserved Windows device name.")
        extension = PurePosixPath(output_name).suffix.lower()
        if extension in {".png", ".jpg", ".jpeg", ".exr", ".tif", ".tiff"}:
            tokens = re.findall(r"\[(#+)\]", output_name)
            stripped = re.sub(r"\[#+\]", "", output_name)
            if len(tokens) != 1 or not 1 <= len(tokens[0]) <= 12 or any(char in stripped for char in "[]#"):
                raise ValidationError("Image-sequence output_name must include exactly one valid [####] numbering token.")
        elif extension not in {".mov", ".avi", ".mp4"}:
            raise ValidationError("Unsupported output file extension.")
        elif any(char in output_name for char in "[]#"):
            raise ValidationError("Movie output_name cannot include a frame-numbering token.")
        for key in ("output_module", "render_settings"):
            if key in options:
                safe_text(options[key], key)
        for key in ("start_frame", "end_frame"):
            if key in options and (type(options[key]) is not int or abs(options[key]) > 2147483647):
                raise ValidationError(key + " must be a 32-bit integer.")
        if ("start_frame" in options and "end_frame" in options
                and options["start_frame"] > options["end_frame"]):
            raise ValidationError("start_frame must not exceed end_frame (inclusive).")
        if input_path.suffix.lower() not in {".aep", ".aepx"}:
            raise ValidationError("ae-render input must be .aep or .aepx.")
    return input_path, options


class Worker:
    def __init__(self, root: Path, config: dict | None = None, *, simulate: bool = False,
                 runner: Callable | None = None):
        self.root = initialize(Path(root))
        self.config = config or {}
        self.simulate = simulate
        self.runner = runner
        self.lock_path = self.root / ".worker.lock"
        self.owns_lock = False

    def __enter__(self):
        try:
            with self.lock_path.open("x", encoding="utf-8") as stream:
                json.dump({"pid": os.getpid(), "host": socket.gethostname(), "started_at": timestamp()}, stream)
        except FileExistsError as exc:
            raise WorkerBlocked("Worker lock exists. Do not remove it until the previous worker and Adobe job are confirmed stopped.") from exc
        self.owns_lock = True
        try:
            self.check_recovery()
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *_):
        if self.owns_lock:
            self.lock_path.unlink(missing_ok=True)
            self.owns_lock = False

    def status_path(self, job_id: str) -> Path:
        return self.root / "status" / (job_id + ".json")

    def block(self, job_id: str, message: str) -> None:
        atomic_json(self.root / "blocked.json", {"job_id": job_id, "reason": message, "at": timestamp(),
                    "recovery": "Confirm Adobe is idle and inspect outputs/logs. Preserve unknown status; use a new id to retry. Remove blocked.json only after review."})

    def check_recovery(self) -> None:
        if (self.root / "blocked.json").exists():
            raise WorkerBlocked("blocked.json exists: a prior job may still be running in Adobe. Review it before restarting.")
        for pending in (self.root / "processing").glob("*.json"):
            job_id = self.file_id(pending)
            path = self.status_path(job_id)
            status = read_json(path) if path.exists() else {}
            if status.get("state") in TERMINAL and status.get("state") != "unknown":
                self.archive(pending)
                continue
            message = "Worker stopped while a job was claimed. Native execution state is unknown; no automatic retry."
            atomic_json(path, {"id": job_id, "state": "unknown", "finished_at": timestamp(), "error": message})
            self.block(job_id, message)
            # Preserve the claimed manifest as evidence but remove it from the
            # recovery scan. After manual host review, removing blocked.json
            # must permit fresh job ids without repeatedly blocking this one.
            self.archive(pending)
            raise WorkerBlocked(message)

    @staticmethod
    def file_id(path: Path) -> str:
        if valid_job_id(path.stem):
            return path.stem
        return "invalid-" + hashlib.sha256(path.name.encode("utf-8")).hexdigest()[:20]

    def archive(self, path: Path, *, rejected: bool = False) -> None:
        folder = self.root / ("rejected" if rejected else "archive")
        target = folder / (self.file_id(path) + "-" + uuid.uuid4().hex + ".json")
        os.replace(path, target)

    def process_job(self, pending: Path) -> dict:
        if not self.owns_lock:
            raise WorkerBlocked("Acquire the worker lock before processing jobs.")
        initialize(self.root)  # Refuse shared-folder directory symlink substitutions.
        job_id = self.file_id(pending)
        status_path = self.status_path(job_id)
        if status_path.exists() or status_path.is_symlink():
            self.archive(pending, rejected=True)
            return {"id": job_id, "state": "duplicate", "error": "Existing job status preserved. Use a fresh id."}
        claimed = self.root / "processing" / pending.name
        if claimed.exists() or claimed.is_symlink():
            raise WorkerBlocked("An earlier claimed manifest exists; inspect processing/ before continuing.")
        os.replace(pending, claimed)
        status = {"id": job_id, "state": "validating", "started_at": timestamp()}
        atomic_json(status_path, status)
        native_started = False
        try:
            job = read_json(claimed)
            input_path, options = validate_job(job, claimed.name, self.root)
            status.update({"action": job["action"], "input": job["input"]})
            if self.simulate:
                status.update({"state": "simulated", "native_executed": False, "outputs": [],
                               "message": "Manifest validated only. No Adobe application was called and no artwork was produced."})
            else:
                output_dir = self.root / "outputs" / job_id
                output_dir.mkdir(exist_ok=False)
                log_path = self.root / "logs" / (job_id + ".log")
                if log_path.exists() or log_path.is_symlink():
                    raise ValidationError("Log already exists for this job id; use a new id.")
                status.update({"state": "running", "native_execution_requested": True, "log": f"logs/{job_id}.log"})
                atomic_json(status_path, status)
                runner = self.runner
                if runner is None:
                    try:
                        from .adobe_adapter import run as runner
                    except ImportError:
                        from adobe_adapter import run as runner
                native_started = True
                results = runner(job["action"], input_path, output_dir, options, self.config, log_path)
                if not isinstance(results, list) or not results:
                    raise RuntimeError("Adobe adapter returned no output files.")
                verified = []
                for item in results:
                    output = Path(item).resolve()
                    if (not output.is_relative_to(output_dir.resolve()) or not output.is_file()
                            or output.stat().st_size == 0):
                        raise RuntimeError("Output is missing, empty or outside the job output directory.")
                    verified.append(output.relative_to(self.root).as_posix())
                status.update({"state": "succeeded", "native_executed": True, "outputs": verified})
        except (KeyboardInterrupt, SystemExit) as exc:
            status.update({"state": "unknown" if native_started else "failed",
                           "error": "Worker interrupted; native work may continue." if native_started else "Worker interrupted before native execution."})
            if native_started:
                self.block(job_id, status["error"])
            status["finished_at"] = timestamp()
            atomic_json(status_path, status)
            self.archive(claimed)
            raise
        except Exception as exc:
            uncertain = exc.__class__.__name__ == "TimeoutMayStillRun" or getattr(exc, "host_may_still_run", False)
            status.update({"state": "unknown" if uncertain else ("failed" if native_started else "rejected"),
                           "error": str(exc), "outputs": []})
            if uncertain:
                self.block(job_id, str(exc))
        status["finished_at"] = timestamp()
        atomic_json(status_path, status)
        self.archive(claimed, rejected=status["state"] == "rejected")
        if status["state"] == "unknown":
            raise WorkerBlocked("Native job state is unknown; worker stopped. Inspect blocked.json.")
        return status

    def drain(self) -> list[dict]:
        results = []
        for path in sorted((self.root / "queue").glob("*.json")):
            if path.name.startswith("."):
                continue
            try:
                results.append(self.process_job(path))
            except FileNotFoundError:
                # A producer may withdraw an unclaimed file; never retry claimed work.
                if (self.root / "processing" / path.name).exists():
                    raise
        return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path, help="Shared local queue folder")
    parser.add_argument("--config", type=Path, help="Local adapter settings; required for native execution")
    parser.add_argument("--init", action="store_true", help="Create queue directories and exit")
    parser.add_argument("--once", action="store_true", help="Process the current queue snapshot and exit")
    parser.add_argument("--simulate", action="store_true", help="Validate manifests; do not run Adobe")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args(argv)
    if args.poll_seconds < 0.1 or args.poll_seconds > 60:
        parser.error("--poll-seconds must be between 0.1 and 60")
    try:
        if args.init:
            print(json.dumps({"root": str(initialize(args.root)), "state": "initialized"}))
            return 0
        if not args.simulate and args.config is None:
            parser.error("--config is required for native execution")
        config = read_json(args.config) if args.config else {}
        def stop(_signum, _frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, stop)
        with Worker(args.root, config, simulate=args.simulate) as worker:
            while True:
                for result in worker.drain():
                    # JSON escapes keep console output portable to legacy Windows
                    # encodings; the status files themselves remain UTF-8.
                    print(json.dumps(result, ensure_ascii=True), flush=True)
                if args.once:
                    return 0
                time.sleep(args.poll_seconds)
    except KeyboardInterrupt:
        print("Worker stopped. Check status/ and blocked.json before retrying active work.", file=sys.stderr)
        return 130
    except (OSError, ValidationError, WorkerBlocked) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
