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

BTOP_TEXT = "#d7d7d7"
BTOP_MUTED = "#6f6f6f"
BTOP_GREEN = "#78d98b"
BTOP_BORDER_GREEN = "#4f8f68"
BTOP_YELLOW = "#d8c45a"
BTOP_BORDER_YELLOW = "#8d8f48"
BTOP_CYAN = "#38d8e8"
BTOP_BLUE = "#58a6ff"
BTOP_MAGENTA = "#d55ad9"
BTOP_RED = "#f05b6e"


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


def calculate_memory_percent(gpu_stats) -> float:
    mem_used = getattr(gpu_stats, "memory_used", 0) or 0
    mem_total = getattr(gpu_stats, "memory_total", 0) or 0
    if mem_total <= 0:
        return 0.0
    return mem_used / mem_total * 100.0


def format_memory_value(memory_mb: Optional[float]) -> str:
    if memory_mb is None:
        return "N/A"
    if memory_mb >= 1024:
        return f"{memory_mb / 1024:.1f}G"
    return f"{memory_mb:.0f}M"


def format_power_summary(gpu_stats) -> str:
    power_usage = getattr(gpu_stats, "power_usage", None)
    power_limit = getattr(gpu_stats, "power_limit", None)
    if power_usage is not None and power_limit:
        return f"{power_usage:.1f}W/{power_limit:.0f}W"
    if power_usage is not None:
        return f"{power_usage:.1f}W"
    return "N/A"


def format_fan_summary(gpu_stats, show_rpm: bool = True) -> str:
    fan_speed = getattr(gpu_stats, "fan_speed", None)
    fan_speed_rpm = getattr(gpu_stats, "fan_speed_rpm", None)
    if fan_speed is not None and fan_speed_rpm is not None and show_rpm:
        return f"{fan_speed_rpm}RPM/{fan_speed}%"
    if fan_speed is not None:
        return f"{fan_speed}%"
    return "N/A"


def render_bar(percent: float, width: int) -> str:
    width = max(width, 4)
    filled = int(width * max(0.0, min(percent, 100.0)) / 100.0)
    return "━" * filled + "·" * (width - filled)


def render_dots(percent: float, width: int) -> str:
    """Render a compact btop-style dotted activity strip."""
    width = max(width, 4)
    filled = int(width * max(0.0, min(percent, 100.0)) / 100.0)
    return "⠿" * filled + "·" * (width - filled)


def make_widget_line(message: str, style: str, content_width: int) -> Text:
    """Create a single bordered line with truncated content."""
    return Text(f"│ {truncate_text(message, content_width)}", style=style)


def build_separator(style: str, content_width: int) -> Text:
    """Create a separator for compatibility renderers."""
    return Text("├" + "─" * (content_width + 1), style=style)


def build_box_lines(title: str, lines: list[Text], width: int, style: str = "cyan") -> list[Text]:
    """Render btop-like bordered text block lines."""
    content_width = max(width - 2, 16)
    title_label = f" {title} "
    if len(title_label) >= content_width:
        title_label = title_label[:content_width]
    title_style = f"bold {BTOP_TEXT}"
    border_style = style
    top = Text.assemble(
        Text("┌", style=border_style),
        Text(title_label, style=title_style),
        Text("─" * max(content_width - len(title_label), 0), style=border_style),
        Text("┐", style=border_style),
    )
    bottom = Text.assemble(
        Text("└", style=border_style),
        Text("─" * content_width, style=border_style),
        Text("┘", style=border_style),
    )
    rendered = [top]
    for line in lines:
        text = truncate_text(str(line), content_width)
        line_style = getattr(line, "style", None) or BTOP_TEXT
        rendered.append(
            Text.assemble(
                Text("│", style=border_style),
                Text(f"{text:<{content_width}}", style=line_style),
                Text("│", style=border_style),
            )
        )
    rendered.append(bottom)
    return rendered


def make_box(title: str, lines: list[Text], width: int, style: str = "cyan") -> Text:
    """Render a btop-like bordered text block."""
    rendered = build_box_lines(title, lines, width, style)
    return Text("\n").join(rendered)


def build_meter_content_lines(gpus, selected_gpu_id, layout: GPUDashboardLayout) -> list[Text]:
    """Render all-GPU selection rows for standalone and embedded meters."""
    lines = [Text("gpu   util                  mem   temp    power", style=f"bold {BTOP_GREEN}")]
    for gpu in gpus:
        util = getattr(gpu, "utilization", 0) or 0
        mem_percent = calculate_memory_percent(gpu)
        temp = format_optional_number(getattr(gpu, "temperature", None), "C")
        power_usage = getattr(gpu, "power_usage", None)
        power = format_optional_number(power_usage, "W") if power_usage is not None else "N/A"
        marker = "›" if gpu.gpu_id == selected_gpu_id else " "
        row = (
            f"{marker}{gpu.gpu_id:<3} "
            f"{render_bar(util, layout.meter_bar_width)} {util:>3}% "
            f"{mem_percent:>4.0f}% {temp:>5} {power:>6}"
        )
        lines.append(Text(row, style=f"bold {BTOP_GREEN}" if marker == "›" else BTOP_TEXT))
        memory_row = (
            f"    mem {render_bar(mem_percent, layout.meter_bar_width)} "
            f"{format_memory_value(getattr(gpu, 'memory_used', 0)):>6}/"
            f"{format_memory_value(getattr(gpu, 'memory_total', 0)):<6}"
        )
        lines.append(Text(memory_row, style=BTOP_YELLOW))
    return lines


def overlay_right_panel(
    base_lines: list[Text],
    overlay_lines: list[Text],
    content_width: int,
    gap: int = 2,
    right_margin: int = 1,
) -> list[Text]:
    """Place a short right-side panel inside a wider btop-style region."""
    if not overlay_lines:
        return base_lines

    overlay_width = max(len(str(line)) for line in overlay_lines)
    overlay_start = max(0, content_width - overlay_width - right_margin)
    base_width = max(0, overlay_start - gap)
    row_count = max(len(base_lines), len(overlay_lines))
    rendered = []

    for row_index in range(row_count):
        base_line = base_lines[row_index] if row_index < len(base_lines) else Text("")
        overlay_line = overlay_lines[row_index] if row_index < len(overlay_lines) else None
        base_style = getattr(base_line, "style", None) or BTOP_TEXT
        base_text = str(base_line)[:base_width]

        if overlay_line is None:
            rendered.append(Text(f"{str(base_line):<{content_width}}", style=base_style))
            continue

        spacer = " " * max(overlay_start - len(base_text), 0)
        rendered.append(Text.assemble(Text(base_text, style=base_style), Text(spacer), overlay_line, Text(" " * right_margin)))

    return rendered


def build_process_lines(processes, layout: GPUWidgetLayout) -> list[str]:
    """Compatibility renderer for current-user GPU processes."""
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
    """Render selected-GPU processes with a fixed row budget."""
    visible_processes = list(processes)[: layout.process_rows]
    hidden_count = max(len(processes) - len(visible_processes), 0)
    header = "pid     type     gpu mem  command" if layout.show_command_summary else "pid     type     gpu mem  name"
    lines = [Text(header, style=f"bold {BTOP_GREEN}")]

    if not visible_processes:
        lines.append(Text("No current-user GPU processes.", style=BTOP_MUTED))
    else:
        for process in visible_processes:
            pid = getattr(process, "pid", "?")
            process_type = truncate_text(getattr(process, "process_type", "?") or "?", 8)
            process_name = getattr(process, "name", None) or "unknown"
            command_summary = getattr(process, "command_summary", None)
            label = command_summary if layout.show_command_summary and command_summary else process_name
            memory_label = format_process_memory(getattr(process, "used_memory_mb", None))
            lines.append(Text(f"{pid:<7} {process_type:<8} {memory_label:>7}  {label}", style=BTOP_TEXT))

    if hidden_count:
        lines.append(Text(f"... and {hidden_count} more", style=BTOP_MUTED))

    target_rows = layout.process_rows + 1
    while len(lines) < target_rows:
        lines.append(Text(""))

    return lines[:target_rows]


def build_gpu_detail_lines(gpu_stats, layout, util_history, mem_history, graph_style) -> list[Text]:
    """Compatibility single-GPU card renderer."""
    content_width = layout.content_width
    util_value = getattr(gpu_stats, "utilization", 0) or 0
    mem_used = getattr(gpu_stats, "memory_used", 0) or 0
    mem_total = getattr(gpu_stats, "memory_total", 1) or 1
    mem_free = getattr(gpu_stats, "memory_free", 0) or 0
    mem_percent = calculate_memory_percent(gpu_stats)

    lines = [
        Text(f"GPU {gpu_stats.gpu_id}: {gpu_stats.name}", style=f"bold {BTOP_TEXT}"),
        Text(f"GPU Usage: {util_value:>3}% | Memory: {mem_used:.0f}/{mem_total:.0f} MB ({mem_percent:.1f}%) | Free: {mem_free:.0f} MB", style=BTOP_CYAN),
        Text(f"Power: {format_power_summary(gpu_stats)} | Temp: {format_optional_number(getattr(gpu_stats, 'temperature', None), 'C')} | Fan: {format_fan_summary(gpu_stats)}", style=BTOP_GREEN),
    ]

    if layout.show_extended_metrics:
        lines.append(
            Text(
                "Clocks GFX/SM/MEM: "
                f"{format_optional_number(getattr(gpu_stats, 'graphics_clock_mhz', None), 'MHz')} / "
                f"{format_optional_number(getattr(gpu_stats, 'sm_clock_mhz', None), 'MHz')} / "
                f"{format_optional_number(getattr(gpu_stats, 'memory_clock_mhz', None), 'MHz')}",
                style=BTOP_BLUE,
            )
        )

    lines.append(
        Text(
            f"P-State: {getattr(gpu_stats, 'p_state', None) or 'N/A'} | "
            f"PCIe RX/TX: {format_data_rate(getattr(gpu_stats, 'pcie_rx_kbps', None))} / "
            f"{format_data_rate(getattr(gpu_stats, 'pcie_tx_kbps', None))}",
            style=BTOP_TEXT,
        )
    )

    if layout.show_graph:
        lines.append(Text("Utilization", style=f"bold {BTOP_CYAN}"))
        lines.extend(
            create_graph(
                util_history,
                layout.graph_width,
                layout.graph_height,
                100.0,
                ColorTheme.GPU_BLUE,
                graph_style,
            )
        )
        lines.append(Text("Memory", style=f"bold {BTOP_MAGENTA}"))
        lines.extend(
            create_graph(
                mem_history,
                layout.graph_width,
                max(3, layout.graph_height // 2),
                100.0,
                ColorTheme.NPU_MAGENTA,
                graph_style,
            )
        )

    return str(make_box("gpu", lines, content_width + 2, BTOP_BORDER_GREEN)).splitlines()


class TimeWidget(Static):
    """A compact top status and key hint line."""

    def on_mount(self) -> None:
        self.update_timer = self.set_interval(1.0, self.update_time)
        self.update_time()

    def update_time(self) -> None:
        current_time = datetime.now().strftime("%H:%M:%S")
        width = getattr(getattr(self, "size", None), "width", 0) or 96
        left = "¹ gpu  menu  preset 1"
        right = "- 700ms +  q quit  j/k gpu  s graph"
        gap = max(width - len(left) - len(current_time) - len(right), 2)
        left_gap = gap // 2
        right_gap = gap - left_gap
        self.update(
            Text(
                f"{left}{' ' * left_gap}{current_time}{' ' * right_gap}{right}",
                style=f"bold {BTOP_TEXT}",
            )
        )


class StatusWidget(Static):
    """A widget to display startup and availability messages."""

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def render(self) -> RenderableType:
        return make_box("status", [Text(self.message, style=BTOP_YELLOW)], 80, BTOP_BORDER_YELLOW)


class GPUHistoryWidget(Static):
    """Selected GPU long history panel."""

    def __init__(self, graph_style: GraphStyle = GraphStyle.BRAILLE) -> None:
        super().__init__(id="gpu-history")
        self.gpu_stats = None
        self.gpus = []
        self.gpu_count = 0
        self.utilization_history = deque([0.0] * 120, maxlen=120)
        self.memory_history = deque([0.0] * 120, maxlen=120)
        self.graph_style = graph_style
        self.dashboard_layout = resolve_gpu_dashboard_layout(120, 32)

    def update_snapshot(self, gpu_stats, gpu_count, utilization_history, memory_history, graph_style, layout, gpus=None):
        self.gpu_stats = gpu_stats
        self.gpus = list(gpus or [])
        self.gpu_count = gpu_count
        self.utilization_history = utilization_history
        self.memory_history = memory_history
        self.graph_style = graph_style
        self.dashboard_layout = layout
        self.update(self.render_history())

    def render_history(self) -> RenderableType:
        if self.gpu_stats is None:
            return make_box("gpu", [Text("No GPU selected.", style=BTOP_YELLOW)], self.dashboard_layout.history_width, BTOP_BORDER_GREEN)

        util_value = getattr(self.gpu_stats, "utilization", 0) or 0
        mem_percent = calculate_memory_percent(self.gpu_stats)
        content_width = max(self.dashboard_layout.history_width - 2, 16)
        title = f"¹gpu {self.gpu_stats.gpu_id + 1}/{max(self.gpu_count, 1)}"
        meter_overlay = []
        if self.gpus and content_width >= 96:
            meter_overlay = build_box_lines(
                "meters",
                build_meter_content_lines(self.gpus, self.gpu_stats.gpu_id, self.dashboard_layout),
                min(self.dashboard_layout.meter_width, max(38, content_width // 2)),
                BTOP_BORDER_GREEN,
            )
        overlay_width = max((len(str(line)) for line in meter_overlay), default=0)
        graph_gap = 2 if meter_overlay else 0
        primary_graph_width = max(content_width - overlay_width - graph_gap - 1, 24)
        full_graph_width = content_width
        header = (
            f"{truncate_text(self.gpu_stats.name, 28)}  "
            f"util {util_value:>3}%  mem {mem_percent:>3.0f}%  "
            f"temp {format_optional_number(getattr(self.gpu_stats, 'temperature', None), 'C'):>5}  "
            f"power {format_power_summary(self.gpu_stats):>10}"
        )
        graph_lines = create_graph(
            self.utilization_history,
            primary_graph_width,
            self.dashboard_layout.history_height,
            100.0,
            ColorTheme.GPU_BLUE,
            self.graph_style,
        )
        memory_lines = create_graph(
            self.memory_history,
            full_graph_width,
            self.dashboard_layout.memory_graph_height,
            100.0,
            ColorTheme.GPU_YELLOW,
            self.graph_style,
        )
        graph_label_width = primary_graph_width
        memory_label_width = full_graph_width
        lines = [
            Text(truncate_text(header, graph_label_width), style=f"bold {BTOP_TEXT}"),
            Text(f"utilization {render_dots(util_value, max(graph_label_width - 20, 8))} {util_value:>3}%", style=BTOP_CYAN),
        ]
        lines.extend(graph_lines)
        if meter_overlay:
            lines = overlay_right_panel(lines, meter_overlay, content_width)
        lines.append(Text(f"total ▴▾ gpu-totals {render_dots(mem_percent, max(memory_label_width - 31, 8))} {mem_percent:>3.0f}%", style=BTOP_MUTED))
        lines.extend(memory_lines)
        return make_box(title, lines, self.dashboard_layout.history_width, BTOP_BORDER_GREEN)


class GPUMeterWidget(Static):
    """All-GPU compact meter panel."""

    def __init__(self) -> None:
        super().__init__(id="gpu-meters")
        self.gpus = []
        self.selected_gpu_id = 0
        self.dashboard_layout = resolve_gpu_dashboard_layout(120, 32)

    def update_snapshot(self, gpus, selected_gpu_id, layout):
        self.gpus = list(gpus)
        self.selected_gpu_id = selected_gpu_id
        self.dashboard_layout = layout
        self.update(self.render_meters())

    def render_meters(self) -> RenderableType:
        lines = build_meter_content_lines(self.gpus, self.selected_gpu_id, self.dashboard_layout)
        return make_box("meters", lines, self.dashboard_layout.meter_width, BTOP_BORDER_GREEN)


class GPUOverviewWidget(GPUMeterWidget):
    """Backward-compatible name for the all-GPU meter panel."""


class GPUResourceWidget(Static):
    """Selected GPU memory, power and thermal panel."""

    def __init__(self) -> None:
        super().__init__(id="gpu-resources")
        self.gpu_stats = None
        self.dashboard_layout = resolve_gpu_dashboard_layout(120, 32)

    def update_snapshot(self, gpu_stats, layout):
        self.gpu_stats = gpu_stats
        self.dashboard_layout = layout
        self.update(self.render_resources())

    def render_resources(self) -> RenderableType:
        if self.gpu_stats is None:
            return make_box("mem/power", [Text("No GPU selected.", style=BTOP_YELLOW)], self.dashboard_layout.resource_width, BTOP_BORDER_YELLOW)

        mem_used = getattr(self.gpu_stats, "memory_used", 0) or 0
        mem_total = getattr(self.gpu_stats, "memory_total", 0) or 0
        mem_free = getattr(self.gpu_stats, "memory_free", 0) or 0
        mem_percent = calculate_memory_percent(self.gpu_stats)
        power_usage = getattr(self.gpu_stats, "power_usage", None)
        power_limit = getattr(self.gpu_stats, "power_limit", None)
        power_percent = power_usage / power_limit * 100 if power_usage is not None and power_limit else 0
        temp = getattr(self.gpu_stats, "temperature", None)
        temp_percent = min(max(temp or 0, 0), 100)
        fan = format_fan_summary(self.gpu_stats, self.dashboard_layout.show_fan_rpm)
        available = mem_free
        bar_width = max(8, self.dashboard_layout.resource_bar_width - 2)

        lines = [
            Text(f"Total:      {format_memory_value(mem_total):>9}", style=f"bold {BTOP_TEXT}"),
            Text(f"Used:  {render_bar(mem_percent, bar_width)} {format_memory_value(mem_used):>9} {mem_percent:>4.0f}%", style=BTOP_YELLOW),
            Text(f"Available: {format_memory_value(available):>9}", style=BTOP_TEXT),
            Text(f"Free:  {render_dots(100 - mem_percent, bar_width)} {format_memory_value(mem_free):>9}", style=BTOP_CYAN),
            Text(f"Power: {render_bar(power_percent, bar_width)} {format_power_summary(self.gpu_stats):>12}", style=BTOP_RED),
            Text(f"Temp:  {render_bar(temp_percent, bar_width)} {format_optional_number(temp, 'C'):>12}", style=BTOP_GREEN),
            Text(f"Fan:        {fan:>12}", style=BTOP_GREEN),
        ]
        return make_box("mem/power", lines, self.dashboard_layout.resource_width, BTOP_BORDER_YELLOW)


class GPUProcessWidget(Static):
    """Current-user GPU process table."""

    def __init__(self) -> None:
        super().__init__(id="gpu-processes")
        self.processes = []
        self.dashboard_layout = resolve_gpu_dashboard_layout(120, 32)

    def update_snapshot(self, gpu_stats, layout: GPUDashboardLayout) -> None:
        self.processes = list(getattr(gpu_stats, "processes", []))
        self.dashboard_layout = layout
        self.update(self.render_processes())

    def render_processes(self) -> RenderableType:
        return make_box("proc", build_process_panel_lines(self.processes, self.dashboard_layout), self.dashboard_layout.process_width, BTOP_BORDER_GREEN)


class GPUStatusWidget(Static):
    """Bottom device and status line."""

    def __init__(self) -> None:
        super().__init__(id="gpu-status")
        self.gpu_stats = None
        self.status_messages = []
        self.dashboard_layout = resolve_gpu_dashboard_layout(120, 32)

    def update_snapshot(self, gpu_stats, status_messages, layout):
        self.gpu_stats = gpu_stats
        self.status_messages = list(status_messages)
        self.dashboard_layout = layout
        self.update(self.render_status())

    def render_status(self) -> RenderableType:
        if self.gpu_stats is None:
            return make_box("status", [Text("No GPU selected.", style=BTOP_YELLOW)], self.dashboard_layout.status_width, BTOP_BORDER_YELLOW)

        parts = [
            f"GPU {self.gpu_stats.gpu_id}: {self.gpu_stats.name}",
            f"Driver {getattr(self.gpu_stats, 'driver_version', 'N/A')}",
            f"CUDA {getattr(self.gpu_stats, 'cuda_version', 'N/A')}",
            f"CC {getattr(self.gpu_stats, 'cuda_cc', 'N/A')}",
            f"P-State {getattr(self.gpu_stats, 'p_state', None) or 'N/A'}",
        ]
        if self.dashboard_layout.show_pcie:
            parts.append(
                "PCIe RX/TX "
                f"{format_data_rate(getattr(self.gpu_stats, 'pcie_rx_kbps', None))}/"
                f"{format_data_rate(getattr(self.gpu_stats, 'pcie_tx_kbps', None))}"
            )
        if self.status_messages:
            parts.append(" | ".join(self.status_messages))
        return make_box("device/status", [Text("  ".join(parts), style=BTOP_TEXT)], self.dashboard_layout.status_width, BTOP_BORDER_YELLOW)


class GPUDetailWidget(GPUHistoryWidget):
    """Backward-compatible selected-GPU detail widget."""

    def update_snapshot(
        self,
        gpu_stats,
        utilization_history,
        memory_history,
        graph_style: GraphStyle,
        layout: Optional[GPUDashboardLayout] = None,
    ) -> None:
        self.gpu_stats = gpu_stats
        self.gpu_count = 1
        self.utilization_history = utilization_history
        self.memory_history = memory_history
        self.graph_style = graph_style
        if layout is not None:
            self.dashboard_layout = layout
        self.update(self.render_history())

    def render_detail(self) -> RenderableType:
        return self.render_history()


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
            Text(line) for line in build_gpu_detail_lines(
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
