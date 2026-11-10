# Repository working rules

This is a Claude Desktop/Cowork plugin marketplace plus a separately run local Adobe worker.
Read README.md and the plugin's SKILL.md before changing the workflow.

- Keep all native application execution on the workstation where Adobe is installed.
- Preserve the two-layer design: the skill prepares declarative jobs; the worker executes only implemented actions.
- Do not add arbitrary shell commands or arbitrary JSX to job manifests.
- Never save over original projects or claim native verification based on simulation or mocked tests.
- Run `python -m unittest discover -s tests -v` after changing worker code.
- Run `python scripts/check_package.py` before sharing or publishing.
- Keep local config, Adobe files, credentials and job outputs out of the repository.
- This v0.1 is a new baseline. The owner's historical background scripts have not been recovered or migrated.

See docs/PORTING_EXISTING_WORKFLOWS.md to add an existing workflow with its real inputs, outputs and verification.
