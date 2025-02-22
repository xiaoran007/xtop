import curses
import time
from ..backend.gpu import NvidiaGPU
import os
import math


def draw_line_chart(stdscr, data, max_height, max_width, y_offset=0, x_offset=0):
    for i, value in enumerate(data):
        height = int(value / 10) + 1
        for j in range(height):
            y = max_height - j + y_offset
            x = i + x_offset
            if 0 <= y < curses.LINES and 0 <= x < curses.COLS:
                stdscr.addstr(y, x, '█')


def draw_line_chart2(stdscr, data, max_height, max_width, y_offset=0, x_offset=0):
    for i, value in enumerate(data):
        y = max_height - math.ceil(value / 10) + y_offset
        x = i + x_offset
        if 0 <= y < curses.LINES and 0 <= x < curses.COLS:
            stdscr.addstr(y, x, '-')
        if value == 0 and 0 <= max_height + y_offset < curses.LINES and 0 <= x < curses.COLS:
            stdscr.addstr(max_height + y_offset, x, '-')


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

    utilization_history = [[] for _ in range(nvidia_obj.gpu_number)]

    while True:
        stdscr.clear()

        height, width = stdscr.getmaxyx()

        stdscr.addstr(0, 0, message)

        dynamic_data = f"Time: {time.strftime('%Y/%m/%d, %H:%M:%S')}"
        stdscr.addstr(1, 0, dynamic_data)

        nvidia_obj.update()

        position_base = 2
        for i in range(nvidia_obj.gpu_number):
            dTitle = nvidia_obj.gpus[i].getTitle()
            dUtilization = nvidia_obj.gpus[i].getUtilization()
            dPower = nvidia_obj.gpus[i].getPower()
            stdscr.addstr(i+position_base, 0, dTitle)
            stdscr.addstr(i+position_base+1, 4, dUtilization)
            stdscr.addstr(i+position_base+2, 4, dPower)

            utilization_history[i].append(nvidia_obj.gpus[i].utilization)
            if len(utilization_history[i]) > len(dTitle) - 10:
                utilization_history[i].pop(0)

            draw_line_chart(stdscr, utilization_history[i], 10, width - 10, y_offset=i + position_base + 3, x_offset=4)

            if enable_log:
                dir_path = os.path.expanduser("~/xtop")
                os.makedirs(dir_path, exist_ok=True)
                with open(f"{dir_path}/GPU{i}_{magic_number}.csv", "a") as f:
                    f.write(f"{time.time()}, {nvidia_obj.gpus[i].utilization}\n")
                stdscr.addstr(i + position_base + 14, 4, f"File log to {dir_path}/GPU{i}_{magic_number}.csv")
                position_base += 15

            position_base += 14

        key = stdscr.getch()
        if key == ord('q'):
            break

        stdscr.refresh()

        time.sleep(0.5)

    nvidia_obj.shutdown()

