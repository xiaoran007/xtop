"""
A modern TUI for xtop using Textual.
"""
import sys
from collections import deque
from datetime import datetime

from rich.console import RenderableType
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Footer, Header, Static

# Add project root to path to allow imports from backend
sys.path.append('/Users/xiaoran/Desktop/code/xtop/src')

from xtop.backend.gpu.nvidia import NvidiaGPU, GPUStats
from xtop.backend.cpu.macos import MacOSCPU, CPUStats


# Unicode block characters for graph drawing (btop style)
GRAPH_CHARS_BRAILLE = ['⠀', '⡀', '⡄', '⡆', '⡇', '⣇', '⣧', '⣷', '⣿']
GRAPH_CHARS_BLOCKS = ['⠀', '▁', '▂', '▃', '▄', '▅', '▆', '▇', '█']
GRAPH_HEIGHT = 8  # Height of the graph in characters


def create_btop_net_graph(values: deque, width: int, height: int = 10, max_value: float = 100.0, base_color: str = "cyan", style: str = "block") -> list:
    """
    Create a btop-style vertical bar graph with gradient colors.
    Bars grow upward, with newest data on the right, scrolling left over time.
    
    Args:
        values: deque of historical values
        width: width of the graph in characters (number of bars)
        height: height of the graph in lines (default 10)
        max_value: maximum value for scaling
        base_color: base color name (cyan, green, etc.)
        style: character style - "block" for ░▒▓█ or "braille" for Braille characters
    
    Returns:
        list of Text objects, one per line with gradient colors
    """
    if not values or width < 2 or height < 1:
        return [Text(" " * width) for _ in range(height)]
    
    # Choose character set based on style
    if style == "braille":
        # Braille characters for smoother, more refined appearance
        CHARS = [
            ' ',      # 0/8
            '⢀',      # 1/8
            '⢠',      # 2/8
            '⢰',      # 3/8
            '⢸',      # 4/8
            '⣀',      # 5/8
            '⣄',      # 6/8
            '⣤',      # 7/8
            '⣴',      # Full
        ]
    else:  # block style (default)
        # Block characters with increasing density
        CHARS = [
            ' ',      # 0/8 - Empty
            '░',      # 1/8 - Light shade
            '░',      # 2/8 - Light shade
            '▒',      # 3/8 - Medium shade
            '▒',      # 4/8 - Medium shade
            '▓',      # 5/8 - Dark shade
            '▓',      # 6/8 - Dark shade
            '█',      # 7/8 - Almost full
            '█',      # 8/8 - Full block
        ]
    
    # Define gradient color schemes based on base color (bottom to top)
    if base_color == "cyan" or base_color == "blue":
        # Blue gradient scheme (dark blue -> bright cyan -> white)
        colors = [
            "color(17)",   # Dark blue
            "color(18)",   # Blue
            "color(19)",   # Medium blue
            "color(20)",   # Bright blue
            "color(27)",   # Dodger blue
            "color(33)",   # Deep sky blue
            "color(39)",   # Light blue
            "color(45)",   # Cyan
            "color(51)",   # Bright cyan
            "bright_cyan", # Very bright cyan
            "white"        # White peak
        ]
    elif base_color == "green":
        # Purple/Magenta gradient scheme (dark purple -> bright magenta -> white)
        colors = [
            "color(53)",   # Dark purple
            "color(54)",   # Purple
            "color(55)",   # Medium purple
            "color(92)",   # Deep purple
            "color(93)",   # Light purple
            "color(99)",   # Purple violet
            "color(129)",  # Magenta purple
            "color(165)",  # Magenta
            "color(171)",  # Orchid
            "bright_magenta", # Bright magenta
            "white"        # White peak
        ]
    elif base_color == "magenta" or base_color == "purple":
        # Purple to magenta gradient
        colors = [
            "color(53)",
            "color(54)",
            "color(92)",
            "color(93)",
            "color(129)",
            "magenta",
            "color(165)",
            "color(171)",
            "bright_magenta",
            "white"
        ]
    else:
        colors = [base_color] * (height + 1)
    
    # Ensure we have enough colors for the height
    while len(colors) < height + 1:
        colors.append(colors[-1])
    
    # Get the most recent 'width' values (newest on the right)
    recent_values = list(values)[-width:]
    if len(recent_values) < width:
        recent_values = [0.0] * (width - len(recent_values)) + recent_values
    
    # Build the graph line by line (top to bottom)
    lines = []
    for row in range(height):
        line_chars = []
        # Current row's threshold (from top: height-1 to bottom: 0)
        row_from_bottom = height - 1 - row
        
        for val in recent_values:
            # Normalize value to height
            normalized = min(val / max_value, 1.0)
            bar_height = normalized * height
            
            # Determine what character to show at this row
            if bar_height > row_from_bottom + 1:
                # Full block
                char = CHARS[-1]
            elif bar_height > row_from_bottom:
                # Partial block
                partial = (bar_height - row_from_bottom) * len(CHARS)
                char_idx = min(int(partial), len(CHARS) - 1)
                char = CHARS[char_idx]
            else:
                # Empty
                char = ' '
            
            line_chars.append(char)
        
        # Join all characters for this row
        line_str = ''.join(line_chars)
        
        # Apply gradient color (top rows get brighter colors)
        color_idx = min(height - 1 - row, len(colors) - 1)
        color = colors[color_idx]
        lines.append(Text(line_str, style=f"bold {color}"))
    
    return lines


class GPUStatsWidget(Static):
    """A widget to display GPU statistics."""

    def __init__(self, gpu_stats: GPUStats) -> None:
        super().__init__()
        self.gpu_stats = gpu_stats
        self.utilization_history = deque([0.0] * 80, maxlen=80)
        self.graph_style = "block"  # Default style

    def on_mount(self) -> None:
        """Set up a timer to update the widget."""
        self.update_timer = self.set_interval(0.5, self.update_stats)

    def update_stats(self) -> None:
        """Update the statistics."""
        self.utilization_history.append(self.gpu_stats.utilization or 0.0)
        self.update(self.render_stats())

    def render_stats(self) -> RenderableType:
        """Render the GPU statistics."""
        # Title
        title = Text.from_markup(f"[bold cyan]┃ GPU {self.gpu_stats.gpu_id}: {self.gpu_stats.name}[/bold cyan]")
        
        # Stats
        util_value = self.gpu_stats.utilization or 0
        util_label = Text(f"┃ GPU Usage: {util_value:>3}%", style="cyan")
        
        mem_used = self.gpu_stats.memory_used or 0
        mem_total = self.gpu_stats.memory_total or 1
        mem_percent = mem_used / mem_total * 100
        mem_label = Text(f"┃ Memory:    {mem_used:.0f}/{mem_total:.0f}MB ({mem_percent:.1f}%)", style="cyan")
        
        power_temp_label = Text(f"┃ Power: {self.gpu_stats.power_usage or 0}W | Temp: {self.gpu_stats.temperature or 0}°C", style="cyan")
        
        if self.gpu_stats.fan_speed is not None:
            fan_label = Text(f"┃ Fan: {self.gpu_stats.fan_speed}%", style="cyan")
        else:
            fan_label = Text("┃ Fan: N/A", style="cyan")
        
        # Create btop-style vertical bar graph for utilization (switchable style)
        # width=70 means showing 70 historical data points, height=11 for better resolution
        util_graph_lines = create_btop_net_graph(self.utilization_history, 70, 11, 100.0, "blue", self.graph_style)
        
        # Add border to each graph line
        util_graph_display = []
        for line in util_graph_lines:
            util_graph_display.append(Text.assemble(Text("┃ ", style="cyan"), line))
        
        separator = Text("┃" + "─" * 78, style="cyan")
        
        result_lines = [
            separator,
            title,
            separator,
            util_label,
        ]
        result_lines.extend(util_graph_display)
        result_lines.extend([
            Text("┃", style="cyan"),
            mem_label,
            power_temp_label,
            fan_label,
            separator
        ])
        
        return Text("\n").join(result_lines)


class CPUStatsWidget(Static):
    """A widget to display CPU statistics."""

    def __init__(self, cpu_stats: CPUStats) -> None:
        super().__init__()
        self.cpu_stats = cpu_stats
        self.utilization_history = deque([0.0] * 80, maxlen=80)
        self.graph_style = "block"  # Default style

    def on_mount(self) -> None:
        """Set up a timer to update the widget."""
        self.update_timer = self.set_interval(0.5, self.update_stats)

    def update_stats(self) -> None:
        """Update the statistics."""
        self.utilization_history.append(self.cpu_stats.utilization or 0.0)
        self.update(self.render_stats())

    def render_stats(self) -> RenderableType:
        """Render the CPU statistics."""
        # Title
        title = Text.from_markup(
            f"[bold green]┃ CPU {self.cpu_stats.cpu_id}: {self.cpu_stats.name} "
            f"({self.cpu_stats.cores}C/{self.cpu_stats.threads}T)[/bold green]"
        )
        
        # Stats
        util_value = self.cpu_stats.utilization or 0
        util_label = Text(f"┃ CPU Usage: {util_value:>5.1f}%", style="green")
        
        freq_value = self.cpu_stats.frequency or 0
        freq_label = Text(f"┃ Frequency: {freq_value:>4.2f}GHz", style="green")
        
        temp_value = self.cpu_stats.temperature or 0
        temp_label = Text(f"┃ Temp:      {temp_value:>5.1f}°C", style="green")
        
        power_label = Text(f"┃ Power: {self.cpu_stats.power_usage or 0}W", style="green")
        
        # Create btop-style vertical bar graph for utilization (switchable style)
        # width=70 means showing 70 historical data points, height=11 for better resolution
        util_graph_lines = create_btop_net_graph(self.utilization_history, 70, 11, 100.0, "green", self.graph_style)
        
        # Add border to each graph line
        util_graph_display = []
        for line in util_graph_lines:
            util_graph_display.append(Text.assemble(Text("┃ ", style="green"), line))
        
        separator = Text("┃" + "─" * 78, style="green")
        
        result_lines = [
            separator,
            title,
            separator,
            util_label,
        ]
        result_lines.extend(util_graph_display)
        result_lines.extend([
            Text("┃", style="green"),
            freq_label,
            temp_label,
            power_label,
            separator
        ])
        
        return Text("\n").join(result_lines)


class XtopTUI(App):
    """A Textual app to monitor hardware stats."""

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("s", "toggle_style", "Toggle Style")
    ]

    def __init__(self):
        super().__init__()
        self.gpu_backend = NvidiaGPU()
        self.cpu_backend = MacOSCPU()
        self.has_gpu = False
        self.has_cpu = False
        self.graph_style = "block"  # "block" or "braille"

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        yield VerticalScroll(id="main-container")
        yield Footer()

    def on_mount(self) -> None:
        """Called when the app is mounted."""
        container = self.query_one("#main-container")
        has_any_hardware = False

        # Try to initialize CPU
        try:
            self.cpu_backend.init()
            self.has_cpu = self.cpu_backend.cpu_number > 0
        except Exception as e:
            self.has_cpu = False

        # Try to initialize GPU
        try:
            self.gpu_backend.init()
            self.has_gpu = self.gpu_backend.gpu_number > 0
        except Exception as e:
            self.has_gpu = False

        # Mount CPU widgets
        if self.has_cpu:
            has_any_hardware = True
            for cpu in self.cpu_backend.cpus:
                container.mount(CPUStatsWidget(cpu))

        # Mount GPU widgets
        if self.has_gpu:
            has_any_hardware = True
            for gpu in self.gpu_backend.gpus:
                container.mount(GPUStatsWidget(gpu))

        # If we have any hardware, set up update timer
        if has_any_hardware:
            self.update_timer = self.set_interval(0.5, self.update_data)
        else:
            container.mount(Static("No supported hardware found."))

    def on_unmount(self) -> None:
        """Called when the app is unmounted."""
        if self.has_cpu:
            self.cpu_backend.shutdown()
        if self.has_gpu:
            self.gpu_backend.shutdown()

    def action_toggle_style(self) -> None:
        """Toggle between block and braille graph styles."""
        self.graph_style = "braille" if self.graph_style == "block" else "block"
        # Update all widgets to refresh with new style
        for widget in self.query(GPUStatsWidget):
            widget.graph_style = self.graph_style
        for widget in self.query(CPUStatsWidget):
            widget.graph_style = self.graph_style

    def update_data(self) -> None:
        """Update backend data."""
        if self.has_cpu:
            self.cpu_backend.update()
        if self.has_gpu:
            self.gpu_backend.update()


if __name__ == "__main__":
    app = XtopTUI()
    app.run()
