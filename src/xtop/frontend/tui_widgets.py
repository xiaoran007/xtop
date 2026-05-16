from collections import deque
from datetime import datetime
from typing import Optional

from rich.console import RenderableType
from rich.text import Text
from textual.widgets import Static

from .tui_graphs import ColorTheme, GraphStyle, create_graph
from .tui_layout import (
    GPUDashboardLayout,
    GPUWidgetLayout,
    format_data_rate,
    format_optional_number,
    format_process_memory,
    resolve_gpu_dashboard_layout,
    resolve_gpu_widget_layout,
    truncate_text,
)


def make_widget_line(message: str, style: str, content_width: int) -> Text:
    """Create a single bordered line with truncated content."""
    return Text(f"| {truncate_text(message, content_width)}", style=style)


def build_separator(style: str, content_width: int) -> Text:
    """Create a separator for a widget card."""
    return Text("|" + "-" * (content_width + 1), style=style)


def resolve_terminal_height(widget, fallback: int = 28) -> int:
    """Prefer viewport height over the widget's transient auto-layout height."""
    size = getattr(widget, "size", None)
    try:
        screen = getattr(widget, "screen", None)
    except Exception:
        screen = None
    screen_size = getattr(screen, "size", None)
    app_size = getattr(getattr(widget, "app", None), "size", None)

    candidates = [
        getattr(size, "height", 0) or 0,
        getattr(screen_size, "height", 0) or 0,
        getattr(app_size, "height", 0) or 0,
        fallback,
    ]
    return max(candidates)


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


def build_process_panel_lines(processes, layout: GPUDashboardLayout) -> list[Text]:
    """Render selected-GPU processes in a fixed-height left panel."""
    content_width = max(layout.left_width - 2, 28)
    visible_processes = list(processes)[: layout.process_limit]
    hidden_count = max(len(processes) - len(visible_processes), 0)
    lines = [
        Text("Processes", style="bold cyan"),
        Text(truncate_text(f"current user: {len(processes)}", content_width), style="cyan"),
    ]

    if not visible_processes:
        lines.append(Text("No current-user GPU processes.", style="cyan"))
    else:
        for process in visible_processes:
            pid = getattr(process, "pid", "?")
            process_type = truncate_text(getattr(process, "process_type", "?") or "?", 7)
            process_name = truncate_text(getattr(process, "name", None) or "unknown", 12)
            memory_label = format_process_memory(getattr(process, "used_memory_mb", None))
            command_summary = getattr(process, "command_summary", None)

            if layout.show_command_summary and command_summary:
                row = f"{pid:<6} {memory_label:>6} {process_type:<7} {command_summary}"
            else:
                row = f"{pid:<6} {memory_label:>6} {process_type:<7} {process_name}"
            lines.append(Text(truncate_text(row, content_width), style="cyan"))

    if hidden_count:
        lines.append(Text(truncate_text(f"... and {hidden_count} more", content_width), style="cyan"))

    target_rows = layout.process_limit + 3
    while len(lines) < target_rows:
        lines.append(Text(""))

    return lines[:target_rows]


def calculate_memory_percent(gpu_stats) -> float:
    mem_used = getattr(gpu_stats, "memory_used", 0) or 0
    mem_total = getattr(gpu_stats, "memory_total", 0) or 0
    if mem_total <= 0:
        return 0.0
    return mem_used / mem_total * 100.0


def format_power_summary(gpu_stats) -> str:
    power_usage = getattr(gpu_stats, "power_usage", None)
    power_limit = getattr(gpu_stats, "power_limit", None)
    if power_usage is not None and power_limit:
        return f"{power_usage:.1f}W / {power_limit:.1f}W ({power_usage / power_limit * 100:.0f}%)"
    if power_usage is not None:
        return f"{power_usage:.1f}W"
    return "N/A"


def format_fan_summary(gpu_stats) -> str:
    fan_speed = getattr(gpu_stats, "fan_speed", None)
    fan_speed_rpm = getattr(gpu_stats, "fan_speed_rpm", None)
    if fan_speed is not None and fan_speed_rpm is not None:
        return f"{fan_speed_rpm} RPM ({fan_speed}%)"
    if fan_speed is not None:
        return f"{fan_speed}%"
    return "N/A"


def render_bar(percent: float, width: int) -> str:
    width = max(width, 4)
    filled = int(width * max(0.0, min(percent, 100.0)) / 100.0)
    return "█" * filled + "░" * (width - filled)


def build_gpu_detail_lines(gpu_stats, layout, util_history, mem_history, graph_style) -> list[Text]:
    content_width = layout.content_width
    util_value = getattr(gpu_stats, "utilization", 0) or 0
    mem_used = getattr(gpu_stats, "memory_used", 0) or 0
    mem_total = getattr(gpu_stats, "memory_total", 1) or 1
    mem_free = getattr(gpu_stats, "memory_free", 0) or 0
    mem_percent = calculate_memory_percent(gpu_stats)

    result_lines = [
        build_separator("cyan", content_width),
        make_widget_line(f"GPU {gpu_stats.gpu_id}: {gpu_stats.name}", "bold cyan", content_width),
    ]

    if layout.show_driver_info:
        result_lines.append(
            make_widget_line(
                f"Driver: {gpu_stats.driver_version} | CUDA: {gpu_stats.cuda_version} | Compute Capability: {gpu_stats.cuda_cc}",
                "cyan",
                content_width,
            )
        )

    result_lines.append(build_separator("cyan", content_width))

    metric_lines = [
        f"GPU Usage: {util_value:>3}% | Memory: {mem_used:.0f}/{mem_total:.0f} MB ({mem_percent:.1f}%) | Free: {mem_free:.0f} MB",
        f"Power: {format_power_summary(gpu_stats)} | Temp: {format_optional_number(getattr(gpu_stats, 'temperature', None), 'C')} | Fan: {format_fan_summary(gpu_stats)}",
    ]

    if layout.show_extended_metrics:
        metric_lines.append(
            "Clocks GFX/SM/MEM: "
            f"{format_optional_number(getattr(gpu_stats, 'graphics_clock_mhz', None), 'MHz')} / "
            f"{format_optional_number(getattr(gpu_stats, 'sm_clock_mhz', None), 'MHz')} / "
            f"{format_optional_number(getattr(gpu_stats, 'memory_clock_mhz', None), 'MHz')}"
        )

    metric_lines.append(
        f"P-State: {getattr(gpu_stats, 'p_state', None) or 'N/A'} | "
        f"PCIe RX/TX: {format_data_rate(getattr(gpu_stats, 'pcie_rx_kbps', None))} / "
        f"{format_data_rate(getattr(gpu_stats, 'pcie_tx_kbps', None))}"
    )

    for line in metric_lines:
        result_lines.append(make_widget_line(line, "cyan", content_width))

    if layout.show_graph:
        result_lines.append(Text("| Utilization", style="cyan"))
        for line in create_graph(
            util_history,
            layout.graph_width,
            layout.graph_height,
            100.0,
            ColorTheme.GPU_BLUE,
            graph_style,
        ):
            result_lines.append(Text.assemble(Text("| ", style="cyan"), line))

        result_lines.append(Text("| Memory", style="magenta"))
        for line in create_graph(
            mem_history,
            layout.graph_width,
            max(3, layout.graph_height // 2),
            100.0,
            ColorTheme.NPU_MAGENTA,
            graph_style,
        ):
            result_lines.append(Text.assemble(Text("| ", style="magenta"), line))

    result_lines.append(build_separator("cyan", content_width))
    return result_lines


class TimeWidget(Static):
    """A widget to display current time and key hints."""

    def on_mount(self) -> None:
        self.update_timer = self.set_interval(1.0, self.update_time)
        self.update_time()

    def update_time(self) -> None:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.update(Text(f"xtop | {current_time} | q quit | j/k or arrows select GPU | s graph style", style="bold yellow"))


class StatusWidget(Static):
    """A widget to display startup and availability messages."""

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def render(self) -> RenderableType:
        separator = Text("|" + "-" * 78, style="yellow")
        body = Text(f"| {self.message}", style="yellow")
        return Text("\n").join([separator, body, separator])


class GPUOverviewWidget(Static):
    """A compact overview of all detected GPUs."""

    def __init__(self) -> None:
        super().__init__(id="gpu-overview")
        self.gpus = []
        self.selected_gpu_id = 0
        self.dashboard_layout = resolve_gpu_dashboard_layout(120, 32)

    def update_snapshot(self, gpus, selected_gpu_id: int, layout: Optional[GPUDashboardLayout] = None) -> None:
        self.gpus = list(gpus)
        self.selected_gpu_id = selected_gpu_id
        if layout is not None:
            self.dashboard_layout = layout
        self.update(self.render_overview())

    def render_overview(self) -> RenderableType:
        width = self.dashboard_layout.left_width
        bar_width = self.dashboard_layout.overview_bar_width
        lines = [
            Text("GPU Overview", style="bold cyan"),
            Text(truncate_text("Sel ID  Util              Mem   Pwr Proc", width - 1), style="cyan"),
        ]

        for gpu in self.gpus:
            util = getattr(gpu, "utilization", 0) or 0
            mem_percent = calculate_memory_percent(gpu)
            power = getattr(gpu, "power_usage", None)
            power_label = "N/A" if power is None else f"{power:.0f}W"
            process_count = len(getattr(gpu, "processes", []))
            marker = ">" if gpu.gpu_id == self.selected_gpu_id else " "
            row = (
                f"{marker}  {gpu.gpu_id:<2} "
                f"{util:>3}% {render_bar(util, bar_width)} "
                f"{mem_percent:>4.0f}% "
                f"{power_label:>5} "
                f"{process_count:>4}"
            )
            lines.append(Text(truncate_text(row, max(width - 1, 28)), style="bold cyan" if marker == ">" else "cyan"))

        return Text("\n").join(lines)


class GPUProcessWidget(Static):
    """Selected GPU process panel with stable row budget."""

    def __init__(self) -> None:
        super().__init__(id="gpu-processes")
        self.processes = []
        self.dashboard_layout = resolve_gpu_dashboard_layout(120, 32)

    def update_snapshot(self, gpu_stats, layout: GPUDashboardLayout) -> None:
        self.processes = list(getattr(gpu_stats, "processes", []))
        self.dashboard_layout = layout
        self.update(self.render_processes())

    def render_processes(self) -> RenderableType:
        return Text("\n").join(build_process_panel_lines(self.processes, self.dashboard_layout))


class GPUDetailWidget(Static):
    """Selected GPU detail panel."""

    def __init__(self, graph_style: GraphStyle = GraphStyle.BRAILLE) -> None:
        super().__init__(id="gpu-detail")
        self.gpu_stats = None
        self.utilization_history = deque([0.0] * 120, maxlen=120)
        self.memory_history = deque([0.0] * 120, maxlen=120)
        self.graph_style = graph_style
        self.dashboard_layout = resolve_gpu_dashboard_layout(120, 32)

    def update_snapshot(
        self,
        gpu_stats,
        utilization_history,
        memory_history,
        graph_style: GraphStyle,
        layout: Optional[GPUDashboardLayout] = None,
    ) -> None:
        self.gpu_stats = gpu_stats
        self.utilization_history = utilization_history
        self.memory_history = memory_history
        self.graph_style = graph_style
        if layout is not None:
            self.dashboard_layout = layout
        self.update(self.render_detail())

    def render_detail(self) -> RenderableType:
        if self.gpu_stats is None:
            return Text("No GPU selected.", style="yellow")

        height = resolve_terminal_height(self)
        dashboard_layout = self.dashboard_layout
        widget_layout = resolve_gpu_widget_layout(dashboard_layout.right_width, height)
        widget_layout.content_width = max(dashboard_layout.right_width - 3, 36)
        widget_layout.graph_width = dashboard_layout.graph_width
        widget_layout.graph_height = dashboard_layout.utilization_graph_height
        widget_layout.process_limit = dashboard_layout.process_limit
        widget_layout.show_driver_info = dashboard_layout.show_driver_info
        widget_layout.show_extended_metrics = dashboard_layout.show_extended_metrics
        widget_layout.show_command_summary = False
        widget_layout.compact_process_rows = dashboard_layout.compact

        return Text("\n").join(
            build_gpu_detail_lines(
                self.gpu_stats,
                widget_layout,
                self.utilization_history,
                self.memory_history,
                self.graph_style,
            )
        )


class GPUStatsWidget(Static):
    """Compatibility widget for rendering a single GPU statistics card."""

    def __init__(self, gpu_stats, graph_style: GraphStyle = GraphStyle.BRAILLE) -> None:
        super().__init__()
        self.gpu_stats = gpu_stats
        self.utilization_history = deque([0.0] * 80, maxlen=80)
        self.memory_history = deque([0.0] * 80, maxlen=80)
        self.graph_style = graph_style

    def on_mount(self) -> None:
        self.update_timer = self.set_interval(0.7, self.update_stats)

    def update_stats(self) -> None:
        self.utilization_history.append(getattr(self.gpu_stats, "utilization", 0) or 0.0)
        self.memory_history.append(calculate_memory_percent(self.gpu_stats))
        self.update(self.render_stats())

    def render_stats(self) -> RenderableType:
        size = getattr(self, "size", None)
        width = getattr(size, "width", 84) or 84
        height = resolve_terminal_height(self)
        layout = resolve_gpu_widget_layout(width, height)
        layout.process_limit = 0
        return Text("\n").join(
            build_gpu_detail_lines(
                self.gpu_stats,
                layout,
                self.utilization_history,
                self.memory_history,
                self.graph_style,
            )
        )


class CPUStatsWidget(Static):
    """Placeholder CPU widget kept for compatibility."""

    def __init__(self, cpu_stats=None, graph_style: GraphStyle = GraphStyle.BRAILLE) -> None:
        super().__init__()
        self.cpu_stats = cpu_stats
        self.graph_style = graph_style

    def render(self) -> RenderableType:
        return Text("CPU monitoring is not implemented yet.", style="yellow")


class NPUStatsWidget(Static):
    """Placeholder NPU widget kept for compatibility."""

    def __init__(self, npu_stats=None, graph_style: GraphStyle = GraphStyle.BRAILLE) -> None:
        super().__init__()
        self.npu_stats = npu_stats
        self.graph_style = graph_style

    def render(self) -> RenderableType:
        return Text("NPU monitoring is available through the existing backend path.", style="magenta")
