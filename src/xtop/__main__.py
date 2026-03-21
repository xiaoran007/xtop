import curses
import argparse
import sys

from . import __version__
from .xtopUtil import getOS


def resolve_tui_targets(os_name, args):
    """Resolve which monitors the Textual TUI should request."""
    if args.gpu:
        return True, False, False
    if args.npu:
        return False, False, True
    if os_name == "macos":
        return False, True, False
    return True, False, False


def run_tui(args):
    """Run the modern Textual UI with platform-aware defaults."""
    from .frontend.tui import XtopTUI

    enable_gpu, enable_cpu, enable_npu = resolve_tui_targets(getOS(), args)
    app = XtopTUI(enable_gpu=enable_gpu, enable_cpu=enable_cpu, enable_npu=enable_npu)
    app.run()


def run_gpu_curses(enable_log):
    """Run the legacy curses GPU UI with Jetson detection."""
    try:
        from .backend.gpu.jetson import JetsonGPU

        if JetsonGPU.is_jetson_device():
            from .frontend.gpu import GPU_UI_Jetson

            curses.wrapper(GPU_UI_Jetson, enable_log)
            return
    except ImportError:
        pass

    try:
        from .frontend.gpu import GPU_UI

        curses.wrapper(GPU_UI, enable_log)
    except ImportError as exc:
        print(f"GPU monitoring is unavailable on this system: {exc}")
        sys.exit(1)


def run_npu_curses(enable_log):
    """Run the legacy curses NPU UI."""
    try:
        from .frontend.npu import NPU_UI

        curses.wrapper(NPU_UI, enable_log)
    except ImportError as exc:
        print(f"NPU monitoring is unavailable on this system: {exc}")
        sys.exit(1)


def main():
    os_name = getOS()
    if os_name not in ["linux", "windows", "macos"]:
        print(f"Only Linux, Windows, and macOS is supported for now. Current OS: {os_name}")
        return

    parser = argparse.ArgumentParser(prog="xtop", description="xpu Performance Monitor")
    parser.add_argument("-g", "--gpu", action="store_true", help="Monitoring the GPU")
    parser.add_argument("-n", "--npu", action="store_true", help="Monitoring the NPU (Not available on Windows)")
    parser.add_argument("-l", "--log", action="store_true", help="Create a log file (Experimental)")
    parser.add_argument("-t", "--tui", action="store_true", help="Use the modern Textual TUI")
    parser.add_argument("-v", "--version", action="version", version=f"xtop version: {__version__}")

    args = parser.parse_args()

    if args.tui:
        try:
            run_tui(args)
        except ImportError as e:
            print(e)
            sys.exit(1)
        return

    if args.gpu:
        run_gpu_curses(args.log)
    elif args.npu:
        if os_name == "windows":
            print("NPU is not supported on Windows.")
            sys.exit(1)
        run_npu_curses(args.log)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
