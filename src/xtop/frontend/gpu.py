import curses
import time
from ..backend.gpu import NvidiaGPU
import os


def GPU_UI(stdscr, enable_log=False):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(500)

    if enable_log:
        message = "xtop Terminal UI For GPU (Log Enable)"
    else:
        message = "xtop Terminal UI For GPU"

    magic_number = int(time.time())

    nvidia_obj = NvidiaGPU()
    nvidia_obj.init()
    nvidia_obj.update()

    while True:
        stdscr.clear()

        height, width = stdscr.getmaxyx()

        stdscr.addstr(0, 0, message)

        dynamic_data = f"Time: {time.strftime('%Y/%m/%d, %H:%M:%S')}"
        stdscr.addstr(1, 0, dynamic_data)

        nvidia_obj.update()

        position_base = 2
        for i in range(nvidia_obj.gpu_number):
            stdscr.addstr(i+position_base, 0, nvidia_obj.gpus[i].getTitle())
            stdscr.addstr(i+position_base+1, 4, nvidia_obj.gpus[i].getData())
            if enable_log:
                dir_path = os.path.expanduser("~/xtop")
                os.makedirs(dir_path, exist_ok=True)
                with open(f"{dir_path}/GPU{i}_{magic_number}.csv", "a") as f:
                    f.write(f"{time.time()}, {nvidia_obj.gpus[i].utilization}\n")
                stdscr.addstr(i + position_base + 2, 4, f"File log to {dir_path}/GPU{i}_{magic_number}.csv")
                position_base += 3

            position_base += 2

        key = stdscr.getch()
        if key == ord('q'):
            break

        stdscr.refresh()

        time.sleep(0.5)

    nvidia_obj.shutdown()

