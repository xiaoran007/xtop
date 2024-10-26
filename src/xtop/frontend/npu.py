import curses
import time
from ..backend.npu import IntelNPU


def NPU_UI(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(500)

    intel_obj = IntelNPU()
    intel_obj.init()
    intel_obj.update()

    while True:
        stdscr.clear()

        height, width = stdscr.getmaxyx()

        message = "xtop Terminal UI For NPU"
        stdscr.addstr(0, 0, message)

        dynamic_data = f"Time: {time.strftime('%Y/%m/%d, %H:%M:%S')}"
        stdscr.addstr(1, 0, dynamic_data)

        intel_obj.update()

        position_base = 2
        for i in range(intel_obj.npu_number):
            stdscr.addstr(i+position_base, 0, intel_obj.npus[i].getTitle())
            stdscr.addstr(i+position_base+1, 4, intel_obj.npus[i].getData())
            position_base += 2

        key = stdscr.getch()
        if key == ord('q'):
            break

        stdscr.refresh()

        time.sleep(0.5)

    intel_obj.shutdown()



