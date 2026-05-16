from collections import deque
from enum import Enum

from rich.text import Text
from textual.color import Color


class GraphStyle(Enum):
    """Graph rendering styles."""

    BLOCK = "block"
    BRAILLE = "braille"


class ColorTheme(Enum):
    """Color themes for different hardware types."""

    GPU_BLUE = "blue"
    GPU_GREEN = "green"
    GPU_YELLOW = "yellow"
    CPU_PURPLE = "purple"
    NPU_MAGENTA = "magenta"

    def get_base_color(self) -> Color:
        """Get the base Color object for this theme."""
        if self == ColorTheme.GPU_BLUE:
            return Color.parse("#40c4ff")
        if self == ColorTheme.GPU_GREEN:
            return Color.parse("#78d98b")
        if self == ColorTheme.GPU_YELLOW:
            return Color.parse("#d8c45a")
        if self == ColorTheme.CPU_PURPLE:
            return Color.parse("#a78bfa")
        if self == ColorTheme.NPU_MAGENTA:
            return Color.parse("#ec5f8f")
        return Color.parse("#40c4ff")


def create_graph(
    values: deque,
    width: int,
    height: int = 10,
    max_value: float = 100.0,
    color_theme: ColorTheme = ColorTheme.GPU_BLUE,
    style: GraphStyle = GraphStyle.BRAILLE,
) -> list:
    """Create a compact vertical history graph."""
    if not values or width < 2 or height < 1:
        return [Text(" " * width) for _ in range(height)]

    if style == GraphStyle.BRAILLE:
        chars = [" ", "⠂", "⠆", "⡀", "⡄", "⣀", "⣄", "⣤", "⣴"]
    else:
        chars = [" ", "░", "░", "▒", "▒", "▓", "▓", "█", "█"]

    base_color = color_theme.get_base_color()
    colors = []
    for index in range(height + 1):
        brightness_ratio = 0.85 - (0.35 * index / max(height, 1))
        colors.append(base_color.lighten(brightness_ratio - 0.5).hex)

    recent_values = list(values)[-width:]
    if len(recent_values) < width:
        recent_values = [0.0] * (width - len(recent_values)) + recent_values

    lines = []
    for row in range(height):
        row_from_bottom = height - 1 - row
        line_chars = []
        for value in recent_values:
            normalized = min(max(value, 0.0) / max_value, 1.0)
            bar_height = normalized * height
            if bar_height < 1.0 and value >= 0:
                bar_height = 1.0

            if bar_height > row_from_bottom + 1:
                char = chars[-1]
            elif bar_height > row_from_bottom:
                partial = (bar_height - row_from_bottom) * len(chars)
                char = chars[min(int(partial), len(chars) - 1)]
            else:
                char = " "
            line_chars.append(char)

        color = colors[min(height - 1 - row, len(colors) - 1)]
        lines.append(Text("".join(line_chars), style=f"bold {color}"))

    return lines
