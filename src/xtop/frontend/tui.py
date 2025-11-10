"""
A modern TUI for xtop using Textual.
"""
from collections import deque
from enum import Enum

from rich.console import RenderableType
from rich.text import Text
from textual.app import App, ComposeResult
from textual.color import Color
from textual.containers import VerticalScroll
from textual.widgets import Footer, Header, Static

from xtop.backend.gpu.nvidia import NvidiaGPU, GPUStats
from xtop.backend.cpu.apple import AppleCPU, CPUStats
from xtop.backend.npu.intel import IntelNPU, NPUStats


class GraphStyle(Enum):
    """Graph rendering styles."""
    BLOCK = "block"
    BRAILLE = "braille"


class ColorTheme(Enum):
    """Color themes for different hardware types."""
    GPU_BLUE = "blue"
    CPU_PURPLE = "purple"
    NPU_MAGENTA = "magenta"

    def get_base_color(self) -> Color:
        """Get the base Color object for this theme."""
        if self == ColorTheme.GPU_BLUE:
            return Color.parse("#EC4899")  # 00FFFF
        elif self == ColorTheme.CPU_PURPLE:
            return Color.parse("#A855F7")  # A855F7
        elif self == ColorTheme.NPU_MAGENTA:
            return Color.parse("#EC4899")  # EC4899
        else:
            return Color.parse("#06B6D4")


def create_graph(values: deque, width: int, height: int = 10, max_value: float = 100.0, 
                color_theme: ColorTheme = ColorTheme.GPU_BLUE, style: GraphStyle = GraphStyle.BRAILLE) -> list:
    """
    Create a btop-style vertical bar graph with gradient colors.
    Bars grow upward, with newest data on the right, scrolling left over time.
    
    Args:
        values: deque of historical values
        width: width of the graph in characters (number of bars)
        height: height of the graph in lines (default 10)
        max_value: maximum value for scaling
        color_theme: ColorTheme enum for gradient colors
        style: GraphStyle enum - BLOCK for ░▒▓█ or BRAILLE for Braille characters
    
    Returns:
        list of Text objects, one per line with gradient colors
    """
    if not values or width < 2 or height < 1:
        return [Text(" " * width) for _ in range(height)]
    
    # Choose character set based on style
    if style == GraphStyle.BRAILLE:
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
    
    # Generate gradient colors by adjusting brightness of base color
    base_color = color_theme.get_base_color()
    colors = []
    
    # Create gradient from darker to lighter (bottom to top of graph)
    # Using brightness range from 0.5 to 0.85 for good visibility in both themes
    num_colors = height + 1
    for i in range(num_colors):
        # Brightness decreases from bottom (0.85) to top (0.5)
        brightness_ratio = 0.85 - (0.35 * i / max(num_colors - 1, 1))
        # Use darken/lighten to adjust brightness
        adjusted_color = base_color.lighten(brightness_ratio - 0.5)
        colors.append(adjusted_color.hex)
    
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
            
            # Add baseline: ensure minimum 1 block height for visibility (even at 0%)
            if bar_height < 1.0 and val >= 0:
                bar_height = 1.0
            
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

    def __init__(self, gpu_stats: GPUStats, graph_style: GraphStyle = GraphStyle.BRAILLE) -> None:
        super().__init__()
        self.gpu_stats = gpu_stats
        self.utilization_history = deque([0.0] * 80, maxlen=80)
        self.graph_style = graph_style

    def on_mount(self) -> None:
        """Set up a timer to update the widget."""
        self.update_timer = self.set_interval(0.7, self.update_stats)

    def update_stats(self) -> None:
        """Update the statistics."""
        self.utilization_history.append(self.gpu_stats.utilization or 0.0)
        self.update(self.render_stats())

    def render_stats(self) -> RenderableType:
        """Render the GPU statistics."""
        # Title
        title = Text.from_markup(f"[bold cyan]┃ GPU {self.gpu_stats.gpu_id}: {self.gpu_stats.name}[/bold cyan]")
        
        # Driver and CUDA info
        driver_info = Text(
            f"┃ Driver: {self.gpu_stats.driver_version} | CUDA: {self.gpu_stats.cuda_version} | Compute Capability: {self.gpu_stats.cuda_cc}",
            style="cyan"
        )
        
        # Stats
        util_value = self.gpu_stats.utilization or 0
        util_label = Text(f"┃ GPU Usage: {util_value:>3}%", style="cyan")
        
        mem_used = self.gpu_stats.memory_used or 0
        mem_total = self.gpu_stats.memory_total or 1
        mem_percent = mem_used / mem_total * 100
        mem_label = Text(f"┃ Memory: {mem_used:.0f} /。{mem_total:.0f}MB ({mem_percent:.1f}%)", style="cyan")
        
        power_temp_label = Text(f"┃ Power: {self.gpu_stats.power_usage or 0}W | Temp: {self.gpu_stats.temperature or 0}°C", style="cyan")
        
        if self.gpu_stats.fan_speed is not None and self.gpu_stats.fan_speed_rpm is not None:
            fan_label = Text(f"┃ Fan: {self.gpu_stats.fan_speed_rpm} RPM ({self.gpu_stats.fan_speed}%)", style="cyan")
        elif self.gpu_stats.fan_speed is not None:
            fan_label = Text(f"┃ Fan: {self.gpu_stats.fan_speed}%", style="cyan")
        else:
            fan_label = Text("┃ Fan: N/A (Fanless GPU)", style="cyan")
        
        # Create btop-style vertical bar graph with GPU blue theme
        util_graph_lines = create_graph(
            self.utilization_history, 76, 11, 100.0, 
            ColorTheme.GPU_BLUE, self.graph_style
        )
        
        # Add border to each graph line
        util_graph_display = []
        for line in util_graph_lines:
            util_graph_display.append(Text.assemble(Text("┃ ", style="cyan"), line))
        
        separator = Text("┃" + "─" * 78, style="cyan")
        
        result_lines = [
            separator,
            title,
            driver_info,
            separator,
            util_label,
            mem_label,
            power_temp_label,
            fan_label,
            Text("┃", style="cyan"),
        ]
        result_lines.extend(util_graph_display)
        result_lines.append(separator)
        
        return Text("\n").join(result_lines)


class CPUStatsWidget(Static):
    """A widget to display CPU statistics."""

    def __init__(self, cpu_stats: CPUStats, graph_style: GraphStyle = GraphStyle.BRAILLE) -> None:
        super().__init__()
        self.cpu_stats = cpu_stats
        self.utilization_history = deque([0.0] * 80, maxlen=80)
        self.graph_style = graph_style

    def on_mount(self) -> None:
        """Set up a timer to update the widget."""
        self.update_timer = self.set_interval(0.7, self.update_stats)

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
        
        # Create btop-style vertical bar graph with CPU purple theme
        util_graph_lines = create_graph(
            self.utilization_history, 70, 11, 100.0, 
            ColorTheme.CPU_PURPLE, self.graph_style
        )
        
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
            freq_label,
            temp_label,
            power_label,
            Text("┃", style="green"),
        ]
        result_lines.extend(util_graph_display)
        result_lines.append(separator)
        
        return Text("\n").join(result_lines)


class NPUStatsWidget(Static):
    """A widget to display NPU statistics."""

    def __init__(self, npu_stats: NPUStats, graph_style: GraphStyle = GraphStyle.BRAILLE) -> None:
        super().__init__()
        self.npu_stats = npu_stats
        self.utilization_history = deque([0.0] * 80, maxlen=80)
        self.graph_style = graph_style

    def on_mount(self) -> None:
        """Set up a timer to update the widget."""
        self.update_timer = self.set_interval(0.7, self.update_stats)

    def update_stats(self) -> None:
        """Update the statistics."""
        self.utilization_history.append(self.npu_stats.utilization or 0.0)
        self.update(self.render_stats())

    def render_stats(self) -> RenderableType:
        """Render the NPU statistics."""
        # Title
        title = Text.from_markup(f"[bold magenta]┃ NPU {self.npu_stats.npu_id}: {self.npu_stats.name}[/bold magenta]")
        
        # Stats
        util_value = self.npu_stats.utilization or 0
        util_label = Text(f"┃ NPU Usage: {util_value:>3}%", style="magenta")
        
        mem_used = self.npu_stats.memory_used or 0
        mem_total = self.npu_stats.memory_total or 1
        mem_percent = mem_used / mem_total * 100 if mem_total > 0 else 0
        mem_label = Text(f"┃ Memory:    {mem_used:.0f}/{mem_total:.0f}MB ({mem_percent:.1f}%)", style="magenta")
        
        # Create btop-style vertical bar graph with NPU magenta theme
        util_graph_lines = create_graph(
            self.utilization_history, 70, 11, 100.0, 
            ColorTheme.NPU_MAGENTA, self.graph_style
        )
        
        # Add border to each graph line
        util_graph_display = []
        for line in util_graph_lines:
            util_graph_display.append(Text.assemble(Text("┃ ", style="magenta"), line))
        
        separator = Text("┃" + "─" * 78, style="magenta")
        
        result_lines = [
            separator,
            title,
            separator,
            util_label,
            mem_label,
            Text("┃", style="magenta"),
        ]
        result_lines.extend(util_graph_display)
        result_lines.append(separator)
        
        return Text("\n").join(result_lines)


class XtopTUI(App):
    """A Textual app to monitor hardware stats."""

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("s", "toggle_graph_style", "Toggle Graph Style"),
        ("ctrl+t", "toggle_dark", "Toggle Dark/Light Mode")
    ]

    def __init__(self, enable_gpu: bool = True, enable_cpu: bool = True, enable_npu: bool = False):
        super().__init__()
        self.enable_gpu = enable_gpu
        self.enable_cpu = enable_cpu
        self.enable_npu = enable_npu
        self.gpu_backend = NvidiaGPU() if enable_gpu else None
        self.cpu_backend = AppleCPU() if enable_cpu else None
        self.npu_backend = IntelNPU() if enable_npu else None
        self.has_gpu = False
        self.has_cpu = False
        self.has_npu = False
        self.graph_style = GraphStyle.BRAILLE  # Start with braille style

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        yield VerticalScroll(id="main-container")
        yield Footer()

    def on_mount(self) -> None:
        """Called when the app is mounted."""
        container = self.query_one("#main-container")
        has_any_hardware = False

        # Try to initialize CPU (only if enabled)
        if self.enable_cpu:
            try:
                self.cpu_backend.init()
                self.has_cpu = self.cpu_backend.cpu_number > 0
            except Exception:
                self.has_cpu = False

        # Try to initialize GPU (only if enabled)
        if self.enable_gpu:
            try:
                self.gpu_backend.init()
                self.has_gpu = self.gpu_backend.gpu_number > 0
            except Exception:
                self.has_gpu = False

        # Try to initialize NPU (only if enabled)
        if self.enable_npu:
            try:
                self.npu_backend.init()
                self.has_npu = self.npu_backend.npu_number > 0
            except Exception:
                self.has_npu = False

        # Mount CPU widgets
        if self.has_cpu:
            has_any_hardware = True
            for cpu in self.cpu_backend.cpus:
                container.mount(CPUStatsWidget(cpu, self.graph_style))

        # Mount GPU widgets
        if self.has_gpu:
            has_any_hardware = True
            for gpu in self.gpu_backend.gpus:
                container.mount(GPUStatsWidget(gpu, self.graph_style))

        # Mount NPU widgets
        if self.has_npu:
            has_any_hardware = True
            for npu in self.npu_backend.npus:
                container.mount(NPUStatsWidget(npu, self.graph_style))

        # If we have any hardware, set up update timer
        if has_any_hardware:
            self.update_timer = self.set_interval(0.7, self.update_data)
        else:
            container.mount(Static("No supported hardware found."))

    def on_unmount(self) -> None:
        """Called when the app is unmounted."""
        if self.has_cpu:
            self.cpu_backend.shutdown()
        if self.has_gpu:
            self.gpu_backend.shutdown()
        if self.has_npu:
            self.npu_backend.shutdown()

    def action_toggle_graph_style(self) -> None:
        """Toggle between block and braille graph styles."""
        self.graph_style = GraphStyle.BLOCK if self.graph_style == GraphStyle.BRAILLE else GraphStyle.BRAILLE
        
        # Update all widgets to use the new graph style
        for widget in self.query(GPUStatsWidget):
            widget.graph_style = self.graph_style
        for widget in self.query(CPUStatsWidget):
            widget.graph_style = self.graph_style
        for widget in self.query(NPUStatsWidget):
            widget.graph_style = self.graph_style

    def update_data(self) -> None:
        """Update backend data."""
        if self.has_cpu:
            self.cpu_backend.update()
        if self.has_gpu:
            self.gpu_backend.update()
        if self.has_npu:
            self.npu_backend.update()


if __name__ == "__main__":
    app = XtopTUI()
    app.run()
