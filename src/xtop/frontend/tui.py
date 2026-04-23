"""
A modern TUI for xtop using Textual.
"""
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import importlib
from typing import Optional

from rich.console import RenderableType
from rich.text import Text
from textual.app import App, ComposeResult
from textual.color import Color
from textual.containers import VerticalScroll
from textual.widgets import Footer, Header, Static

from xtop.xtopUtil import getOS


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


def resolve_cpu_status_message(os_name: str) -> str:
    """Describe the current state of CPU support."""
    if os_name == "macos":
        return "Apple CPU monitoring is not implemented yet."
    return "CPU monitoring is not implemented yet."


def resolve_gpu_unavailable_message(reason: Optional[str] = None) -> str:
    """Describe why GPU monitoring is unavailable."""
    if reason:
        return f"GPU monitoring is unavailable on this system: {reason}"
    return "GPU monitoring is unavailable on this system."


def resolve_npu_unavailable_message(reason: Optional[str] = None) -> str:
    """Describe why NPU monitoring is unavailable."""
    if reason:
        return f"NPU monitoring is unavailable on this system: {reason}"
    return "NPU monitoring is unavailable on this system."


def build_status_messages(
    os_name: str,
    *,
    enable_gpu: bool,
    enable_cpu: bool,
    enable_npu: bool,
    gpu_error: Optional[str] = None,
    npu_error: Optional[str] = None,
) -> list[str]:
    """Collect user-facing status messages for requested monitors."""
    messages = []
    if enable_cpu:
        messages.append(resolve_cpu_status_message(os_name))
    if enable_gpu and gpu_error:
        messages.append(resolve_gpu_unavailable_message(gpu_error))
    if enable_npu and npu_error:
        messages.append(resolve_npu_unavailable_message(npu_error))
    return messages


def load_gpu_backend():
    """Load the GPU backend lazily, preferring Jetson when applicable."""
    try:
        jetson_module = importlib.import_module("xtop.backend.gpu.jetson")
        if jetson_module.JetsonGPU.is_jetson_device():
            return jetson_module.JetsonGPU(), None
    except Exception:
        pass

    try:
        nvidia_module = importlib.import_module("xtop.backend.gpu.nvidia")
        return nvidia_module.NvidiaGPU(), None
    except ImportError as exc:
        return None, str(exc)
    except Exception:
        return None, "backend could not be loaded"


def load_npu_backend():
    """Load the Intel NPU backend lazily."""
    try:
        npu_module = importlib.import_module("xtop.backend.npu.intel")
        return npu_module.IntelNPU(), None
    except ImportError as exc:
        return None, str(exc)
    except Exception:
        return None, "backend could not be loaded"


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


@dataclass
class GPUWidgetLayout:
    content_width: int
    graph_width: int
    graph_height: int
    process_limit: int
    show_driver_info: bool
    show_extended_metrics: bool
    show_command_summary: bool
    show_graph: bool
    compact_process_rows: bool


def truncate_text(value: str, max_width: int) -> str:
    """Truncate text to the available width."""
    if max_width <= 0:
        return ""
    if len(value) <= max_width:
        return value
    if max_width <= 3:
        return value[:max_width]
    return value[: max_width - 3] + "..."


def format_optional_number(value, suffix: str = "", precision: int = 0) -> str:
    """Format a number when available."""
    if value is None:
        return "N/A"
    if precision == 0:
        return f"{int(value)}{suffix}"
    return f"{value:.{precision}f}{suffix}"


def format_data_rate(kbps: Optional[int]) -> str:
    """Format a PCIe throughput value."""
    if kbps is None:
        return "N/A"
    if kbps >= 1024:
        return f"{kbps / 1024:.1f} MB/s"
    return f"{kbps} KB/s"


def resolve_gpu_widget_layout(width: int, height: int) -> GPUWidgetLayout:
    """Choose a GPU card layout that matches the available widget size."""
    content_width = max(width - 3, 36)
    compact = content_width < 78
    show_extended_metrics = content_width >= 96
    show_driver_info = content_width >= 68
    show_command_summary = content_width >= 104
    show_graph = width >= 52 and height >= 18

    if height >= 34:
        process_limit = 5
        graph_height = 11
    elif height >= 28:
        process_limit = 4
        graph_height = 9
    elif height >= 22:
        process_limit = 3
        graph_height = 7
    else:
        process_limit = 2
        graph_height = 5

    if compact:
        process_limit = min(process_limit, 2)
        graph_height = min(graph_height, 5)

    if not show_graph:
        graph_height = 0

    graph_width = max(content_width - 1, 24)

    return GPUWidgetLayout(
        content_width=content_width,
        graph_width=graph_width,
        graph_height=graph_height,
        process_limit=process_limit,
        show_driver_info=show_driver_info,
        show_extended_metrics=show_extended_metrics,
        show_command_summary=show_command_summary,
        show_graph=show_graph,
        compact_process_rows=compact,
    )


def make_widget_line(message: str, style: str, content_width: int) -> Text:
    """Create a single bordered line with truncated content."""
    return Text(f"┃ {truncate_text(message, content_width)}", style=style)


def build_separator(style: str, content_width: int) -> Text:
    """Create a separator for a widget card."""
    return Text("┃" + "─" * (content_width + 1), style=style)


def format_process_memory(memory_mb: Optional[float]) -> str:
    """Format per-process GPU memory usage."""
    if memory_mb is None:
        return "N/A"
    if memory_mb >= 1024:
        return f"{memory_mb / 1024:.1f}G"
    return f"{memory_mb:.0f}M"


def build_process_lines(processes, layout: GPUWidgetLayout) -> list[str]:
    """Render current-user GPU processes into compact, width-aware rows."""
    total = len(processes)
    if total == 0:
        return ["Processes (current user): 0", "No current-user GPU processes."]

    lines = [f"Processes (current user): {total}"]
    visible_processes = processes[: layout.process_limit]

    for process in visible_processes:
        pid = getattr(process, "pid", "?")
        username = truncate_text(getattr(process, "username", "?") or "?", 12)
        process_type = truncate_text(getattr(process, "process_type", "?") or "?", 8)
        process_name = getattr(process, "name", None) or "unknown"
        command_summary = getattr(process, "command_summary", None)
        memory_label = format_process_memory(getattr(process, "used_memory_mb", None))

        if layout.compact_process_rows:
            line = f"PID {pid} | {memory_label:>5} | {process_name}"
        else:
            line = f"PID {pid:<7} {username:<12} {memory_label:>6} {process_type:<8} {process_name}"

        if layout.show_command_summary and command_summary and command_summary != process_name:
            line = f"{line} | {command_summary}"

        lines.append(line)

    hidden_count = total - len(visible_processes)
    if hidden_count > 0:
        lines.append(f"... and {hidden_count} more process(es)")

    return lines


def resolve_terminal_height(widget, fallback: int = 28) -> int:
    """Prefer viewport height over the widget's transient auto-layout height."""
    size = getattr(widget, "size", None)
    screen_size = getattr(getattr(widget, "screen", None), "size", None)
    app_size = getattr(getattr(widget, "app", None), "size", None)

    candidates = [
        getattr(size, "height", 0) or 0,
        getattr(screen_size, "height", 0) or 0,
        getattr(app_size, "height", 0) or 0,
        fallback,
    ]
    return max(candidates)


class TimeWidget(Static):
    """A widget to display current time."""

    def on_mount(self) -> None:
        """Set up a timer to update the time."""
        self.update_timer = self.set_interval(1.0, self.update_time)
        self.update_time()

    def update_time(self) -> None:
        """Update the time display."""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.update(Text(f"⏰ {current_time}", style="bold yellow"))


class StatusWidget(Static):
    """A widget to display startup and availability messages."""

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def render(self) -> RenderableType:
        separator = Text("┃" + "─" * 78, style="yellow")
        body = Text(f"┃ {self.message}", style="yellow")
        return Text("\n").join([separator, body, separator])


class GPUStatsWidget(Static):
    """A widget to display GPU statistics."""

    def __init__(self, gpu_stats, graph_style: GraphStyle = GraphStyle.BRAILLE) -> None:
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
        size = getattr(self, "size", None)
        width = getattr(size, "width", 84) or 84
        height = resolve_terminal_height(self)
        layout = resolve_gpu_widget_layout(width, height)
        content_width = layout.content_width

        util_value = self.gpu_stats.utilization or 0
        mem_used = getattr(self.gpu_stats, "memory_used", 0) or 0
        mem_total = getattr(self.gpu_stats, "memory_total", 1) or 1
        mem_free = getattr(self.gpu_stats, "memory_free", 0) or 0
        mem_percent = mem_used / mem_total * 100 if mem_total else 0

        power_usage = getattr(self.gpu_stats, "power_usage", None)
        power_limit = getattr(self.gpu_stats, "power_limit", None)
        if power_usage is not None and power_limit:
            power_summary = f"{power_usage:.1f}W / {power_limit:.1f}W ({power_usage / power_limit * 100:.0f}%)"
        elif power_usage is not None:
            power_summary = f"{power_usage:.1f}W"
        else:
            power_summary = "N/A"

        fan_speed = getattr(self.gpu_stats, "fan_speed", None)
        fan_speed_rpm = getattr(self.gpu_stats, "fan_speed_rpm", None)
        if fan_speed is not None and fan_speed_rpm is not None:
            fan_summary = f"{fan_speed_rpm} RPM ({fan_speed}%)"
        elif fan_speed is not None:
            fan_summary = f"{fan_speed}%"
        else:
            fan_summary = "N/A"

        title = make_widget_line(
            f"GPU {self.gpu_stats.gpu_id}: {self.gpu_stats.name}",
            "bold cyan",
            content_width,
        )

        result_lines = [build_separator("cyan", content_width), title]

        if layout.show_driver_info:
            result_lines.append(
                make_widget_line(
                    f"Driver: {self.gpu_stats.driver_version} | CUDA: {self.gpu_stats.cuda_version} | Compute Capability: {self.gpu_stats.cuda_cc}",
                    "cyan",
                    content_width,
                )
            )

        result_lines.append(build_separator("cyan", content_width))

        metric_lines = [
            f"GPU Usage: {util_value:>3}% | Memory: {mem_used:.0f}/{mem_total:.0f} MB ({mem_percent:.1f}%) | Free: {mem_free:.0f} MB",
            f"Power: {power_summary} | Temp: {format_optional_number(getattr(self.gpu_stats, 'temperature', None), '°C')} | Fan: {fan_summary}",
        ]

        if layout.show_extended_metrics:
            metric_lines.append(
                "Clocks GFX/SM/MEM: "
                f"{format_optional_number(getattr(self.gpu_stats, 'graphics_clock_mhz', None), 'MHz')} / "
                f"{format_optional_number(getattr(self.gpu_stats, 'sm_clock_mhz', None), 'MHz')} / "
                f"{format_optional_number(getattr(self.gpu_stats, 'memory_clock_mhz', None), 'MHz')}"
            )
            metric_lines.append(
                f"P-State: {getattr(self.gpu_stats, 'p_state', None) or 'N/A'} | "
                f"PCIe RX/TX: {format_data_rate(getattr(self.gpu_stats, 'pcie_rx_kbps', None))} / "
                f"{format_data_rate(getattr(self.gpu_stats, 'pcie_tx_kbps', None))}"
            )
        else:
            metric_lines.append(
                f"P-State: {getattr(self.gpu_stats, 'p_state', None) or 'N/A'} | "
                f"PCIe RX/TX: {format_data_rate(getattr(self.gpu_stats, 'pcie_rx_kbps', None))} / "
                f"{format_data_rate(getattr(self.gpu_stats, 'pcie_tx_kbps', None))}"
            )

        for line in metric_lines:
            result_lines.append(make_widget_line(line, "cyan", content_width))

        result_lines.append(build_separator("cyan", content_width))
        for line in build_process_lines(getattr(self.gpu_stats, "processes", []), layout):
            result_lines.append(make_widget_line(line, "cyan", content_width))

        if layout.show_graph:
            util_graph_lines = create_graph(
                self.utilization_history,
                layout.graph_width,
                layout.graph_height,
                100.0,
                ColorTheme.GPU_BLUE,
                self.graph_style,
            )
            result_lines.append(Text("┃", style="cyan"))
            for line in util_graph_lines:
                result_lines.append(Text.assemble(Text("┃ ", style="cyan"), line))

        result_lines.append(build_separator("cyan", content_width))

        return Text("\n").join(result_lines)


class CPUStatsWidget(Static):
    """A widget to display CPU statistics."""

    def __init__(self, cpu_stats, graph_style: GraphStyle = GraphStyle.BRAILLE) -> None:
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

    def __init__(self, npu_stats, graph_style: GraphStyle = GraphStyle.BRAILLE) -> None:
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
        self.os_name = getOS()
        self.enable_gpu = enable_gpu
        self.enable_cpu = enable_cpu
        self.enable_npu = enable_npu
        self.status_messages = []

        gpu_error = None
        npu_error = None

        if enable_gpu:
            self.gpu_backend, gpu_error = load_gpu_backend()
        else:
            self.gpu_backend = None

        self.cpu_backend = None

        if enable_npu:
            self.npu_backend, npu_error = load_npu_backend()
        else:
            self.npu_backend = None

        self.status_messages.extend(
            build_status_messages(
                self.os_name,
                enable_gpu=enable_gpu,
                enable_cpu=enable_cpu,
                enable_npu=enable_npu,
                gpu_error=gpu_error,
                npu_error=npu_error,
            )
        )
        self.has_gpu = False
        self.has_cpu = False
        self.has_npu = False
        self.graph_style = GraphStyle.BRAILLE  # Start with braille style

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        yield TimeWidget(id="time-widget")
        yield VerticalScroll(id="main-container")
        yield Footer()

    def on_mount(self) -> None:
        """Called when the app is mounted."""
        container = self.query_one("#main-container")
        has_any_hardware = False

        # Try to initialize CPU (only if enabled)
        if self.enable_cpu:
            self.has_cpu = False

        # Try to initialize GPU (only if enabled)
        if self.enable_gpu and self.gpu_backend is not None:
            gpu_init_failed = False
            try:
                self.gpu_backend.init()
                self.has_gpu = self.gpu_backend.gpu_number > 0
            except Exception:
                self.has_gpu = False
                gpu_init_failed = True
                self.status_messages.append(resolve_gpu_unavailable_message())
            if not gpu_init_failed and not self.has_gpu:
                self.status_messages.append("GPU monitoring requested, but no supported GPU was detected.")

        # Try to initialize NPU (only if enabled)
        if self.enable_npu and self.npu_backend is not None:
            npu_init_failed = False
            try:
                self.npu_backend.init()
                self.has_npu = self.npu_backend.npu_number > 0
            except Exception:
                self.has_npu = False
                npu_init_failed = True
                self.status_messages.append(resolve_npu_unavailable_message())
            if not npu_init_failed and not self.has_npu:
                self.status_messages.append("NPU monitoring requested, but no supported Intel NPU was detected.")

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

        for message in dict.fromkeys(self.status_messages):
            container.mount(StatusWidget(message))

        # If we have any hardware, set up update timer
        if has_any_hardware:
            self.update_timer = self.set_interval(0.7, self.update_data)
        elif not self.status_messages:
            container.mount(StatusWidget("No requested hardware monitors are available."))

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
