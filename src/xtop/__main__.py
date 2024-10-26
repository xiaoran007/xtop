import curses
from .xtopUtil import getOS
from . import __version__
import sys


def main():
    if getOS() != "linux":
        print(f"Only Linux is supported for now. Current OS: {getOS()}")
        return
    if len(sys.argv) == 2:
        if sys.argv[1] == "-g" or sys.argv[1] == "--gpu":
            from .frontend import GPU_UI
            curses.wrapper(GPU_UI)
        elif sys.argv[1] == '-n' or sys.argv[1] == "--npu":
            from .frontend import NPU_UI
            curses.wrapper(NPU_UI)
        elif sys.argv[1] == "-h" or sys.argv[1] == "--help":
            print_help()
        else:
            print("Wrong argument.")
            print_help()
    else:
        print("Wrong argument.")
        print_help()


def print_help():
    print("Usage: xtop [Option]")
    print("Options:")
    print("\t-g, --gpu\tShow GPU information")
    print("\t-n, --npu\tShow NPU information")
    print("\t-h, --help\tShow this help message")
    print(f"xtop version: {__version__}")


if __name__ == "__main__":
    main()



