# Adobe worker job contract

This baseline supports exactly `ae-render` and `ps-export-png`. Use the worker and README from the same repository version as this skill. The worker is a separate local installation, not an executable included in the installed Claude plugin cache.

## Queue layout

All paths below are relative to the configured, shared queue root:

| Path | Purpose |
| --- | --- |
| `inputs/` | Existing source files and their required local assets |
| `queue/` | JSON jobs awaiting the local worker |
| `status/` | Per-job status JSON written by the worker |
| `outputs/` | Produced artifacts |
| `logs/` | Worker and job diagnostics |

Use `status/<id>.json` to follow one job. Read output/log paths from worker results and the README rather than assuming a generated filename.

## Common fields

| Field | Rule |
| --- | --- |
| `id` | Fresh unique ID matching `[A-Za-z0-9_-]{1,64}`; reject Windows device names CON, PRN, AUX, NUL, COM1–9, LPT1–9 (case-insensitive); never reuse an ID |
| `action` | Exactly `ae-render` or `ps-export-png` |
| `input` | Relative path below `inputs/`; use forward slashes; no absolute paths or `..` traversal |
| `options` | Object containing only documented options for the action |

Write UTF-8 JSON to `queue/<id>.json.tmp`, finish writing, then atomically rename to `queue/<id>.json` in the same directory. The final `.json` filename is the submission boundary. Do not overwrite an existing job or status. If atomic rename is unavailable through the session's local file tool, use the local submission method documented in the README.

No command, shell, script, JSX, expression, URL-to-execute, or executable path belongs in a job. Application locations and worker configuration are maintained locally outside the job payload.

## `ae-render`

Render an existing saved composition from an `.aep` or `.aepx`. Use a prepared copy saved with an empty Render Queue. The worker does not inspect existing output modules; extra modules may otherwise write to stored paths. This action does not edit the project or repair missing dependencies.

| Option | Required | Meaning |
| --- | --- | --- |
| `comp` | Yes | Exact existing composition name |
| `output_name` | Yes | Basename only, with `.mov`, `.avi`, `.mp4`, or a `.png` frame-sequence name such as `frame_[####].png` |
| `output_module` | No | Name of an output-module template installed on the local AE machine |
| `render_settings` | No | Name of an installed render-settings template |
| `start_frame` | No | Start frame number accepted by the worker |
| `end_frame` | No | End frame number accepted by the worker; cannot precede `start_frame` |

The filename extension alone does not select a codec or create an output-module template. Confirm the template/format pairing on the actual machine. Do not assume `.mp4` is supported merely because it is an accepted basename extension. PNG sequences require a suitable image-sequence output module. Use saved/default render settings only when they match the user's requested result.

Example, with a template name that must exist locally:

```json
{
  "id": "ae-demo-001",
  "action": "ae-render",
  "input": "inputs/demo.aep",
  "options": {
    "comp": "Main",
    "output_name": "preview.mov",
    "output_module": "YOUR_VERIFIED_MOV_OUTPUT_TEMPLATE"
  }
}
```

Do not submit this example unchanged. Resolve the user's actual file, exact composition, format, and machine's template names, then generate a new ID. AEP assets, fonts, and third-party effects must already be available to After Effects. Check the README and logs for missing-dependency behavior.

## `ps-export-png`

Export the PSD's existing visual composite to PNG through the local Photoshop worker. This action does not export individual layers, replace text, resize the image, or add transparency that the document does not already have. Use the source's existing saved state; no options are supported.

PSD and PSB inputs must be RGB or grayscale, 8-bit or 16-bit. Save and close all Photoshop documents before running a batch. No automatic color-mode/bit-depth conversion is performed.

```json
{
  "id": "ps-demo-001",
  "action": "ps-export-png",
  "input": "inputs/demo.psd",
  "options": {}
}
```

Use the worker-reported output path. Preserve the PSD and verify the PNG actually exists and can be opened when preview tools are available.

## Results and recovery

Read `state` in `status/<id>.json`. States include `validating`, `running`, `succeeded`, `failed`, `rejected`, `simulated` and `unknown`. The only successful terminal result is `succeeded` with verified paths in `outputs`. `simulated` is a dry run and must never be presented as an Adobe export/render. Queue presence, a process ID, and a log saying that execution began are not completion evidence. `unknown` requires local recovery and stops the worker.

For failure or a missing status update, inspect the corresponding log and report the concrete cause or remaining uncertainty. Avoid duplicate submission while the original job may still be active. Follow the worker's documented recovery procedure and use a fresh ID for an authorized retry. Never delete the source, force-close an Adobe application with unsaved work, or silently replace an existing artifact to make a retry appear successful.
