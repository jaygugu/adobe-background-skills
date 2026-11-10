#!/usr/bin/env python3
"""Validate a job and publish complete JSON to a local queue without overwriting."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import uuid

try:
    from .queue_worker import ValidationError, initialize, read_json, validate_job
except ImportError:
    from queue_worker import ValidationError, initialize, read_json, validate_job


def submit(root: Path, job: dict) -> Path:
    root = initialize(root)
    job_id = job.get("id")
    # validate_job handles type/character checks before any path uses this id.
    validate_job(job, str(job_id) + ".json", root)
    final = root / "queue" / (job_id + ".json")
    existing = [final, root / "status" / (job_id + ".json"),
                root / "processing" / (job_id + ".json"),
                root / "outputs" / job_id, root / "logs" / (job_id + ".log")]
    if any(path.exists() or path.is_symlink() for path in existing):
        raise ValidationError("Job id already exists. Use a new id; existing work was preserved.")
    temp = root / "queue" / ("." + job_id + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temp.open("x", encoding="utf-8") as stream:
            json.dump(job, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        try:
            # Hard-link publication is atomic and create-only. os.replace/rename
            # could overwrite another submitter's queued job on POSIX.
            os.link(temp, final)
        except FileExistsError as exc:
            raise ValidationError("A job with this id was submitted concurrently. Existing work was preserved.") from exc
        except OSError as exc:
            raise ValidationError("Atomic queue publication failed. Use a local filesystem supporting hard links (NTFS/APFS/ext4); no unsafe fallback was used.") from exc
    finally:
        temp.unlink(missing_ok=True)
    return final


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="Local queue folder used by the worker")
    parser.add_argument("--job", type=Path, required=True, help="UTF-8 JSON job to submit")
    args = parser.parse_args(argv)
    try:
        job = read_json(args.job)
        path = submit(args.root, job)
        print(json.dumps({"id": job["id"], "state": "queued", "manifest": str(path),
                          "message": "Submitted only; inspect status/<id>.json for the actual execution result."}, ensure_ascii=False))
        return 0
    except (OSError, ValidationError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
