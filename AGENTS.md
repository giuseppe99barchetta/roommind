## Project Scope

This repository is the RoomMind Home Assistant integration.

When working on this project, prioritize small, targeted changes that preserve existing behavior unless the task explicitly requires broader refactoring.

Do not modify unrelated files.

## Repository Search Rules

Avoid unrestricted recursive searches from the repository root.

Never recursively inspect or search inside:

* `.venv/`
* `venv/`
* `.git/`
* `__pycache__/`
* `.pytest_cache/`
* `.mypy_cache/`
* `.ruff_cache/`
* `.coverage`
* `htmlcov/`
* `node_modules/`
* `dist/`
* `build/`
* `target/`
* generated files
* compiled Python files such as `*.pyc`

Prefer `rg` / `ripgrep` for all repository searches.

Examples:

```bash
rg "window|pause|climate" custom_components tests
rg --files custom_components tests
```

If `rg` is unavailable on Windows, do not fall back to an unrestricted:

```powershell
Get-ChildItem -Recurse
```

Instead scope PowerShell searches to likely source directories, for example:

```powershell
Get-ChildItem custom_components,tests -Recurse -File |
    Select-String -Pattern 'window|pause|climate'
```

Always exclude virtual environments, caches, dependencies, generated output, and binary files.

## Context Efficiency

Keep tool output focused and small.

Do not dump entire large files unless necessary.

Prefer:

* targeted symbol searches;
* specific line ranges;
* relevant functions/classes only;
* existing tests related to the feature being changed.

Avoid repeatedly reading the same large file.

When command output is large, narrow the search before continuing instead of requesting larger output.

Do not inspect `.venv`, installed packages, caches, compiled files, or unrelated generated artifacts to understand application behavior.

## Code Changes

Before changing code:

1. Identify the smallest relevant implementation area.
2. Find existing tests for the behavior.
3. Check related configuration/options and UI exposure.
4. Make the smallest coherent implementation.
5. Add or update targeted tests.
6. Run only the relevant tests first.
7. Run broader validation only after targeted tests pass.

Do not perform broad cleanup or refactoring unless explicitly requested.

Preserve backward compatibility where reasonable.

## Home Assistant Integration Guidelines

Follow existing RoomMind patterns for:

* config entries;
* options flow;
* coordinators;
* entity handling;
* climate behavior;
* Home Assistant constants and APIs;
* translations;
* diagnostics;
* tests.

When adding a user-configurable behavior:

* expose it through the existing options/configuration UI when appropriate;
* provide a sensible default;
* preserve existing stored configurations;
* avoid requiring users to recreate the integration;
* add translations for new labels/descriptions;
* add tests for both enabled and disabled states.

## Climate and HVAC Behavior

Treat Home Assistant climate modes carefully.

Do not assume every climate entity supports every HVAC mode.

Use entity-supported modes and existing RoomMind compatibility helpers where available.

Changes involving:

* `off`
* `heat`
* `cool`
* `heat_cool`
* `dry`
* `fan_only`

must avoid altering unrelated HVAC modes.

When implementing window-open behavior, preserve intentional device states unless the configured RoomMind behavior explicitly says otherwise.

## Testing

Prefer focused tests related to the changed feature.

For example:

```bash
pytest tests/coordinator/test_window_pause.py
```

or a specific test:

```bash
pytest tests/coordinator/test_window_pause.py -k fan_only
```

Do not run the entire suite repeatedly during implementation.

Run the full relevant suite once the focused implementation is stable.

Do not inspect or include `__pycache__` or generated test artifacts.

## Windows Environment

This repository is commonly developed on Windows.

Prefer commands that work cleanly in PowerShell.

Use `rg` when available.

When using PowerShell:

* scope searches to known source directories;
* use `Get-Content` only for relevant files;
* use `Select-String` for targeted searches;
* avoid commands that recursively traverse the whole repository without exclusions.

Do not assume Unix-only tools such as `grep`, `sed`, or `awk` are installed.

## Git

Inspect `git status` before changing files.

Do not overwrite unrelated local modifications.

Keep commits focused.

Do not create excessive commits for a single task.

Do not push, merge, rebase, force-push, or open pull requests unless explicitly requested.

## Completion Criteria

A task is complete when:

* the requested behavior is implemented;
* relevant configuration/UI is updated if needed;
* translations are present if needed;
* focused tests cover the change;
* targeted tests pass;
* no unrelated files were modified;
* the final response briefly explains what changed and which tests were run.
