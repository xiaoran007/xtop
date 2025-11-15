# xtop AI Guide

## Quick facts
- CLI entry `src/xtop/__main__.py` exposes `xtop -g|-n|-t|-l`; it defaults to the GPU curses view unless `-t` (Textual UI) is provided and only runs on linux/windows/macos via `xtop.xtopUtil.getOS`.
- Package installs from `pyproject.toml` (`src/` layout) and depends on `pypci-ng`, `nvidia-ml-py`, `textual`, `rich`, plus `windows-curses` on Windows; ensure Python ≥3.9 when spawning tooling.
- Logging writes CSV samples under `~/xtop` when `-l` is passed in curses views; keep this path stable so docs stay accurate.

## Architecture
- Backends live in `src/xtop/backend/**`; each hardware class (e.g., `NvidiaGPU`, `IntelNPU`) implements `init()/update()/shutdown()` and stores `*Stats` holders (`GPUStats`, `NPUStats`) with helper formatters consumed by the UIs.
- GPU monitoring wraps NVML (`pynvml`); remember to call `nvmlInit` once, reuse handles, convert mW to W, and shut down via `nvmlShutdown` in `NvidiaGPU.shutdown`.
- Intel NPU support (`backend/npu/intel.py`) relies on `pypci` to locate devices and reads `/sys` telemetry (`npu_busy_time_us`) to compute utilization deltas—preserve `last_busy_time_*` bookkeeping when adding metrics.
- CPU backend (`backend/cpu/apple.py`) currently emits fake data for the Textual proof-of-concept; its `CPUStats` shape defines what the TUI expects (utilization, per-core history, temp, power).

## Frontends
- Legacy curses dashboards (`frontend/gpu.py`, `frontend/npu.py`) wrap their run loops in `curses.wrapper`, pre-initialize backends, refresh every 500 ms, and optionally log; they expect the backend lists (`.gpus`, `.npus`) to remain stable while updating metrics in place.
- The modern TUI (`frontend/tui.py`) is a Textual `App` that mounts widgets per device type; widgets pull live values from shared backend instances, and periodic refresh happens via `set_interval` timers in both widgets and `XtopTUI.update_data`.
- Graph rendering is centralized in `create_graph` with `GraphStyle`/`ColorTheme`; reuse these instead of crafting new ASCII plots.

## Dev workflows
- Local install for hacking: `pip install -e .` (or `pipx install .`) for CLI access; try `xtop -t -g` for the Textual UI, `xtop -g -l` for GPU logging, and `xtop -n` for the Intel NPU view (fails fast on Windows).
- Build/release via standard tooling: `make build` → `python -m build`, `make upload` → `twine upload dist/*`, `make install` → reinstall wheel; `make clean` removes `dist/`.
- No automated tests yet—validate changes by exercising the relevant UI (curses vs Textual) on actual hardware or by stubbing NVML/pypci calls.
- Running GPU code requires NVML libraries present; when hardware is absent, guard imports or feature-detect in `__main__` so the CLI still prints helpful help text.

## Conventions & tips
- Keep platform/flag logic centralized in `__main__.py` and `xtop.xtopUtil`; if you add hardware, extend flag parsing and gate unsupported OSes early with readable `print` + `sys.exit` rather than raising.
- Follow the stats-holder pattern: update metrics inside backend `update()` and expose presentation helpers (`getTitle`, `getUtilization`, etc.) so frontends stay dumb renderers.
- Prefer timers over threads: curses loops sleep (`time.sleep(0.5)`), Textual widgets use `set_interval`; if you must poll faster, adjust these constants instead of spawning custom loops.
- Logging/telemetry should respect the existing `~/xtop` directory and append CSV rows of `timestamp,value` to keep downstream tooling compatible.
