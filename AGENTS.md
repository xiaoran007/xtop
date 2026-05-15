# AGENTS.md

This file records the long-term collaboration rules for xtop. Any agent working in this repository should read and follow these rules before making changes.

## Project Scope

xtop is a Python command-line hardware monitoring tool distributed primarily through PyPI and pipx. It is intended to monitor CPU, GPU, and NPU resources from normal user space. The main product focus is Nvidia GPU monitoring on Linux and Windows, with additional code paths for NVIDIA Jetson, Intel NPU, and macOS startup behavior.

This is a software package and system utility project, not a research codebase. Changes should prioritize stable CLI behavior, package imports, cross-platform startup paths, and a no-sudo user experience.

## Python Environment

- Use a project-local `.venv` at the repository root by default. Do not rely on conda for this project.
- If `.venv` does not exist, must be recreated, or a Python interpreter needs to be invoked directly, ask the user which Python version or interpreter path to use first.
- After `.venv` exists, run Python, pip, tests, build, and release commands explicitly through `.venv/bin/python` or `.venv/bin/pip`.
- If a required dependency is missing, do not silently downgrade, skip, or work around it. State what is missing and ask the user to approve installation into the project `.venv`.

## Architecture

- Follow the existing project structure for new work:
  - CLI entry points and argument parsing live in `src/xtop/__main__.py`.
  - Hardware collection backends live under `src/xtop/backend/`, split by device type and platform.
  - UI code lives under `src/xtop/frontend/`; the modern TUI uses Textual, while legacy paths use curses.
  - Shared utilities live under `src/xtop/xtopUtil/`; project exceptions live under `src/xtop/xtopException/`.
- Keep hardware backends lazily imported so missing optional platform dependencies do not break unrelated startup paths.
- For Nvidia GPU work, prioritize NVML, current-user GPU processes, training/inference workflows, and terminal-size-aware TUI behavior.
- Keep Jetson, Intel NPU, macOS, and other platform-specific behavior behind clear module boundaries. Avoid scattering platform checks through unrelated modules.

## Testing And Verification

- New behavior must be tested. Prefer the existing unittest-style tests under `tests/`, and add focused tests for startup paths, import behavior, layout calculation, and backend data conversion when useful.
- Before running tests, confirm and use the project `.venv`.
- If a change touches hardware or platform behavior that cannot be verified on the development machine, such as Linux/Windows Nvidia GPUs, Jetson, Intel NPU, or real NVML driver behavior, clearly list the required test machine, operating system, hardware, and commands for the user to run.
- Do not treat macOS startup success as a substitute for target hardware validation. The development machines are macOS, while the primary target is Nvidia GPU monitoring.
- For operations expected to take a long time, provide fine-grained progress output whenever practical.

## Implementation Style

- Avoid excessive fallback logic. Unless a fallback addresses a known platform/API difference or a necessary user experience issue, keep the implementation direct.
- When fallback behavior is necessary, keep it local, explainable, and testable. Prefer fallbacks that protect cross-platform startup paths or known hardware API version differences.
- Keep code simple and focused. Prefer small functions and narrow changes over broad refactors.
- When changing user-visible output, CLI flags, package dependencies, or the support matrix, consider whether README or related documentation should also be updated.
- Do not add Chinese text to project files unless the user explicitly requests it for a specific artifact.

## Permissions And System Boundaries

- xtop is intended to be a pure user-space tool. Running, installing, testing, and developing it should not require `sudo`.
- Do not introduce development paths that require administrator privileges, kernel module installation, system service modification, or global package installation.
- Access to `/sys`, `/proc`, NVML, PCI, and similar system interfaces should be read-only by default. If a platform truly requires additional permissions, explain why and ask the user to arrange validation on the appropriate machine.

## Git Workflow

- This repository uses git. Keep commits small and focused. After completing a clear unit of work, commit it so the change history remains traceable.
- Check `git status` before committing, and never revert or overwrite user changes unless explicitly asked.
- Commit messages should concisely describe the behavior or documentation change.
- If one task contains multiple independent changes, split them into multiple small commits.
