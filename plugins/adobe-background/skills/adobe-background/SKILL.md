---
name: adobe-background
description: Prepare and monitor background Adobe jobs through a separately installed local worker. Use when asked to render an existing After Effects composition from an AEP or export a Photoshop PSD composite to PNG in Claude Desktop or Cowork. Supports only ae-render and ps-export-png; does not provide general Adobe project editing.
---

# Adobe Background Workflows

Treat this as a beta baseline. It is newly packaged functionality, not a recovered collection of the user's earlier workflows. Do not promise that an untested Adobe version, plug-in, output module, or machine configuration works.

## Establish access before submitting work

1. Read the `README.md` in the user's local clone of the GitHub repository. It contains the worker setup and launch instructions. The installed Claude plugin cache contains this skill, not the separately installed `worker/`; do not construct worker paths from the plugin cache.
2. Identify the local queue root that the user configured and shared with Cowork. It contains `inputs/`, `queue/`, `status/`, `outputs/`, and `logs/`. Check that the required input and destination folders are accessible. If the clone or queue location is missing, ask only for that location; never guess a personal filesystem path.
3. Confirm that the local worker was started and determine whether it is running in real or simulated mode using its available status/logs and the README. Folder presence alone does not establish worker health. If unavailable, guide the user through the README's local launch step and continue only after the worker is ready.
4. Verify the actual capabilities exposed in this session. Cowork shell commands may execute in an isolated cloud environment. Never claim that cloud shell access provides access to the workstation's Adobe installation. The supported route here is files exchanged with the separately running Windows/macOS worker; installing the plugin does not install or start Adobe or the worker.

The worker must run on an awake local machine with the relevant Adobe application installed. Keep cloud session capability and local worker capability distinct. Do not enable remote access, change account settings, install software, or start another transport automatically as a substitute for missing access.

## Select a supported operation

Read [the job contract](references/jobs.md) before writing any job.

| Request | Action | Required information |
| --- | --- | --- |
| Render a saved After Effects composition | `ae-render` | `.aep` input, exact composition name, output basename and extension; confirmed output module/settings when needed |
| Export the saved visual composite of a PSD to PNG | `ps-export-png` | `.psd`/`.psb` input; RGB/grayscale 8/16-bit; all Photoshop documents closed |

For requests to change text, replace footage, relink assets, change layer visibility, export individual layers, modify dimensions, edit compositions, or run arbitrary JSX, explain that this package has no corresponding handler yet. Do not approximate these operations with a render/export, silently alter the source, or add an executable payload to a job.

Before AE submission, establish that the input is a prepared copy saved with an empty Render Queue. Existing extra output modules can write to paths stored inside an AEP; the worker does not inspect the project to enforce this condition. If it is unconfirmed, ask for the prepared copy before submitting. For Photoshop, require all documents closed; this baseline does not silently change color mode or bit depth.

## Submit and monitor

1. Submit only when the user has requested the actual supported operation. Explaining setup, inspecting files, or asking what the plugin can do does not authorize a render/export. Routine execution already requested by the user needs no repeated confirmation.
2. Resolve ambiguous inputs and essential missing options before queuing. Use the existing saved project; preserve its source. Place or reference the input under the configured queue root's `inputs/` directory. Preserve the dependent footage hierarchy required by an AEP. Missing fonts, footage, effects, or render templates must be reported rather than invented.
3. Generate a fresh job ID. Create one JSON document matching the contract, with no extra executable fields. Write it in `queue/` as `<id>.json.tmp`, then rename it atomically within that directory to `<id>.json`. If the available file tool cannot perform a reliable same-directory rename, do not write directly to a watched `.json` file; ask the user to submit through the local method in the README.
4. Read `status/<id>.json` and the worker's referenced log after submission. A created job file, a launched process, or elapsed time does not prove success. Poll at reasonable intervals; report the observed state. If the worker has no response, stop resubmitting and diagnose access/worker health. Never queue duplicates merely because a job is slow.
5. Treat simulated output as a dry run only. Report completion only when the worker reports `succeeded` and the actual expected artifacts exist and pass the available checks. Check for nonempty files; for sequences, inspect frame coverage. Preview representative output when the session supports it, and state any checks that could not be performed.
6. If the job fails or stalls, report the relevant error and log location. Do not automatically rerun expensive jobs, kill Adobe, delete partial outputs, or clear the queue. Any retry uses a new ID and follows the README's recovery instructions.

Reply concisely in the user's language: operation, actual status, verified output location, and any limitation that affects the result. Keep source files and private project assets out of GitHub.

## Platform reference

Claude's [plugin support table](https://claude.com/docs/plugins/platform-support) distinguishes local and cloud capabilities. Its [Cowork execution guide](https://support.claude.com/en/articles/13345190-get-started-with-claude-cowork) explains why local file access does not imply that shell commands run on the user's workstation. Check current capabilities instead of assuming parity across installations.
