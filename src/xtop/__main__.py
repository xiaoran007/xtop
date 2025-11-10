import curses
from .xtopUtil import getOS
from . import __version__
import sys
import argparse


def main():
    if getOS() not in ["linux", "windows", "macos"]:
        print(f"Only Linux, Windows, and macOS is supported for now. Current OS: {getOS()}")
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
            from .frontend.tui import XtopTUI
            # Determine what to monitor based on flags
            enable_gpu = False
            enable_cpu = False
            enable_npu = False
            
            # If -g is specified, only monitor GPU
            if args.gpu:
                enable_gpu = True
            # If -n is specified, only monitor NPU
            elif args.npu:
                enable_npu = True
            # If neither is specified, monitor GPU (default)
            else:
                enable_gpu = True
            
            app = XtopTUI(enable_gpu=enable_gpu, enable_cpu=enable_cpu, enable_npu=enable_npu)
            app.run()
        except ImportError as e:
            print(e)
            sys.exit(1)
        return

    if args.gpu:
        from .frontend import GPU_UI
        curses.wrapper(GPU_UI, args.log)
    elif args.npu:
        if getOS() == "windows":
            print("NPU is not supported on Windows.")
            sys.exit(1)
        from .frontend import NPU_UI
        curses.wrapper(NPU_UI, args.log)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

