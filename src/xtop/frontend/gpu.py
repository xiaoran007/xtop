import curses
import time
from ..backend.gpu import NvidiaGPU


def GPU_UI(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(500)

    nvidia_obj = NvidiaGPU()
    nvidia_obj.init()
    nvidia_obj.update()

    while True:
        stdscr.clear()

        height, width = stdscr.getmaxyx()

        message = "xtop Terminal UI For GPU"
        stdscr.addstr(0, 0, message)

        dynamic_data = f"Time: {time.strftime('%Y/%m/%d, %H:%M:%S')}"
        stdscr.addstr(1, 0, dynamic_data)

        nvidia_obj.update()

        position_base = 2
        for i in range(nvidia_obj.gpu_number):
            stdscr.addstr(i+position_base, 0, nvidia_obj.gpus[i].getTitle())
            stdscr.addstr(i+position_base+1, 4, nvidia_obj.gpus[i].getData())
            position_base += 2

        key = stdscr.getch()
        if key == ord('q'):
            break

        stdscr.refresh()

        time.sleep(0.5)

    nvidia_obj.shutdown()

