import curses
from .xtopUtil import getOS
from . import __version__
import sys
import argparse


def main():
    if getOS() != "linux":
        print(f"Only Linux is supported for now. Current OS: {getOS()}")
        return

    parser = argparse.ArgumentParser(prog="xtop", description="xpu information viewer")
    parser.add_argument("-g", "--gpu", action="store_true", help="Show GPU information")
    parser.add_argument("-n", "--npu", action="store_true", help="Show NPU information")
    parser.add_argument("-l", "--log", action="store_true", help="Create a log file")
    parser.add_argument("-v", "--version", action="version", version=f"xtop version: {__version__}")

    args = parser.parse_args()

    if args.gpu:
        from .frontend import GPU_UI
        curses.wrapper(GPU_UI, args.log)
    elif args.npu:
        from .frontend import NPU_UI
        curses.wrapper(NPU_UI, args.log)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

