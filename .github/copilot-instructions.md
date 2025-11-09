# xtop - AI Coding Agent Instructions

## Project Overview
`xtop` is a cross-platform (Linux/Windows) command-line hardware monitoring tool for XPUs (CPU, GPU, NPU). Built with Python and distributed via pip/pipx to avoid requiring admin privileges for installation. Currently supports Nvidia GPU and Intel NPU monitoring.

**Key Design Philosophy**: Python-based tool installable via pip to bypass system package managers and admin requirements—solving the friction of deploying monitoring tools in restricted environments.

## Architecture

### 3-Layer Design Pattern
```
Entry Point (__main__.py)
    ↓
Frontend Layer (frontend/)  ← TUI with curses
    ↓
Backend Layer (backend/)    ← Hardware abstraction
```

**Why this separation**: Enables adding new hardware types (AMD GPU, ARM NPU) by implementing backend interfaces without touching TUI code. Frontend focuses on visualization; backend handles platform-specific APIs.

### Backend Structure
- `backend/gpu/nvidia.py`: Uses `pynvml` library for Nvidia GPU metrics
- `backend/npu/intel.py`: Uses `pypci-ng` library + sysfs (`npu_busy_time_us`) for Intel NPU
- Pattern: Each hardware type has a `Stats` dataclass + manager class (e.g., `NvidiaGPU`, `IntelNPU`)
  - Manager classes implement: `init()`, `update()`, `shutdown()`
  - Stats classes provide: `getTitle()`, formatted display methods

### Frontend Pattern
- `frontend/gpu.py` and `frontend/npu.py` implement curses-based TUIs
- Both follow identical structure: `{DEVICE}_UI(stdscr, enable_log=False)`
- GPU includes ASCII-art line charts for utilization history (10-row height)
- Optional CSV logging to `~/xtop/{DEVICE}{id}_{timestamp}.csv`

## Critical Dependencies

### Platform-Specific
- **Windows**: Requires `windows-curses` (Python's curses doesn't support Windows natively)
  - Auto-installed via `pyproject.toml` conditional dependency
- **Linux**: NPU support only (reads from `/sys/bus/pci/devices/.../npu_busy_time_us`)

### Hardware Libraries
- `pynvml`: Nvidia GPU metrics (utilization, memory, power, temperature, fan)
- `pypci-ng>=0.2.6`: PCI device discovery for NPU (via `PCI().FindAllNPU()`)

## Version Management
**CRITICAL**: Version is defined in TWO places and must stay synchronized:
1. `src/xtop/__init__.py` → `__version__ = "0.3.0"`
2. `pyproject.toml` → `version = "0.3.0"`

When bumping versions, update both files simultaneously.

## Build & Distribution Workflow

```bash
# Build package (uses setuptools via PEP 517)
make build         # Cleans dist/, runs `python -m build`

# Install locally for testing
make install       # Installs built wheel with --force-reinstall

# Publish to PyPI
make upload        # Uses twine (requires credentials)
```

**Entry point**: Configured in `pyproject.toml` as `xtop = "xtop.__main__:main"`

## Development Patterns

### Adding New Hardware Support
1. Create `backend/{type}/{vendor}.py` with `{Vendor}{Type}` manager class
2. Implement `Stats` dataclass with display methods
3. Create `frontend/{type}.py` with `{TYPE}_UI(stdscr, enable_log)` function
4. Add CLI flag in `__main__.py` (follow `-g`/`-n` pattern)
5. Export from `frontend/__init__.py`

### Curses UI Conventions
- Use `stdscr.nodelay(True)` + `stdscr.timeout(500)` for non-blocking input
- Press `q` to quit (checked via `stdscr.getch()`)
- Refresh at 0.5s intervals (`time.sleep(0.5)`)
- Always call hardware shutdown methods before exit

### Error Handling
- Custom exceptions in `xtopException/xtopException.py` (currently unused in code)
- NPU fan speed: Catch `pynvml.NVMLError` for fanless GPUs
- OS validation: Check `getOS()` returns `"linux"` or `"windows"`

## Testing Environment

### Manual Testing Commands
```bash
# GPU monitoring with logging
xtop -g -l

# NPU monitoring (Linux only)
xtop -n

# Show help
xtop -h
```

**Note**: No automated tests exist. Validation requires actual hardware (Nvidia GPU or Intel NPU).

## Common Gotchas

1. **NPU Utilization Calculation**: Uses delta-based calculation from `npu_busy_time_us`
   - First update always returns 0% (no previous timestamp)
   - Formula: `(delta_busy_time_us / delta_timestamp_ms) / 1000`

2. **GPU Line Charts**: Fixed to 10-row height, data truncated to screen width minus 10 chars
   - History array limited by `len(dTitle) - 10`

3. **Cross-Platform Curses**: Always import `curses` directly—`windows-curses` patches it automatically

4. **PCI Device Paths**: Intel NPU code expects pathlib `Path` objects from `pypci-ng`

## File Naming Convention
- Use lowercase with underscores: `nvidia.py`, `xtop_util.py`
- Package names match directory: `xtopUtil/xtopUtil.py`
