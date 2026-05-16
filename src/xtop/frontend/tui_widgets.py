from collections import deque
from datetime import datetime
import os
import socket
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
BTOP_ORANGE = "#f2a65a"


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
        return "n/a"
    if memory_mb >= 1024:
        return f"{memory_mb / 1024:.1f}G"
    return f"{memory_mb:.0f}M"


def format_memory_gib(memory_mb: Optional[float]) -> str:
    if memory_mb is None:
        return "n/a"
    return f"{memory_mb / 1024:.1f}"


def format_power_summary(gpu_stats) -> str:
    power_usage = getattr(gpu_stats, "power_usage", None)
    power_limit = getattr(gpu_stats, "power_limit", None)
    if power_usage is not None and power_limit:
        return f"{power_usage:.1f}W/{power_limit:.0f}W"
    if power_usage is not None:
        return f"{power_usage:.1f}W"
    return "n/a"


def format_fan_summary(gpu_stats, show_rpm: bool = True) -> str:
    fan_speed = getattr(gpu_stats, "fan_speed", None)
    fan_speed_rpm = getattr(gpu_stats, "fan_speed_rpm", None)
    if fan_speed is not None and fan_speed_rpm is not None and show_rpm:
        return f"{fan_speed_rpm}RPM/{fan_speed}%"
    if fan_speed is not None:
        return f"{fan_speed}%"
    return "n/a"


def format_na(value, suffix: str = "", precision: int = 0) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float) and precision > 0:
        return f"{value:.{precision}f}{suffix}"
    if isinstance(value, float):
        return f"{value:.0f}{suffix}"
    return f"{value}{suffix}"


def format_percent(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value:.0f}%"


def calculate_power_percent(gpu_stats) -> float:
    power_usage = getattr(gpu_stats, "power_usage", None)
    power_limit = getattr(gpu_stats, "power_limit", None)
    if power_usage is None or not power_limit:
        return 0.0
    return max(0.0, min(power_usage / power_limit * 100.0, 100.0))


def render_bar(percent: float, width: int) -> str:
    width = max(width, 4)
    filled = int(width * max(0.0, min(percent, 100.0)) / 100.0)
    return "━" * filled + "·" * (width - filled)


def render_dots(percent: float, width: int) -> str:
    """Render a compact btop-style dotted activity strip."""
    width = max(width, 4)
    filled = int(width * max(0.0, min(percent, 100.0)) / 100.0)
    return "⠿" * filled + "·" * (width - filled)


def render_sparkline(values, width: int, max_value: float = 100.0) -> str:
    width = max(width, 4)
    chars = "▁▂▃▄▅▆▇█"
    recent_values = list(values)[-width:]
    if len(recent_values) < width:
        recent_values = [0.0] * (width - len(recent_values)) + recent_values

    rendered = []
    for value in recent_values:
        ratio = min(max((value or 0.0) / max(max_value, 1.0), 0.0), 1.0)
        rendered.append(chars[min(int(ratio * (len(chars) - 1)), len(chars) - 1)])
    return "".join(rendered)


def build_metric_chart(
    label: str,
    values,
    width: int,
    height: int,
    max_value: float,
    current_label: str,
    color_theme: ColorTheme,
    style: GraphStyle,
    color: str,
) -> list[Text]:
    """Build one labeled dashboard chart."""
    content_width = max(width, 24)
    label_width = max(content_width - len(current_label) - 1, 8)
    lines = [
        Text(
            f"{truncate_text(label, label_width):<{label_width}} {current_label}",
            style=f"bold {color}",
        )
    ]
    lines.extend(
        create_graph(
            values,
            content_width,
            height,
            max(max_value, 1.0),
            color_theme,
            style,
        )
    )
    return lines


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
        line_style = getattr(line, "style", None)
        content = line if isinstance(line, Text) and len(str(line)) <= content_width else Text(text, style=line_style or BTOP_TEXT)
        padding = " " * max(content_width - len(str(content)), 0)
        rendered.append(
            Text.assemble(
                Text("│", style=border_style),
                content,
                Text(padding, style=line_style or BTOP_TEXT),
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
    top_offset: int = 0,
) -> list[Text]:
    """Place a short right-side panel inside a wider btop-style region."""
    if not overlay_lines:
        return base_lines

    overlay_width = max(len(str(line)) for line in overlay_lines)
    overlay_start = max(0, content_width - overlay_width - right_margin)
    base_width = max(0, overlay_start - gap)
    row_count = max(len(base_lines), top_offset + len(overlay_lines))
    rendered = []

    for row_index in range(row_count):
        base_line = base_lines[row_index] if row_index < len(base_lines) else Text("")
        overlay_index = row_index - top_offset
        overlay_line = overlay_lines[overlay_index] if 0 <= overlay_index < len(overlay_lines) else None
        base_style = getattr(base_line, "style", None) or BTOP_TEXT
        base_text = str(base_line)[:base_width]

        if overlay_line is None:
            rendered.append(Text(f"{str(base_line):<{content_width}}", style=base_style))
            continue

        spacer = " " * max(overlay_start - len(base_text), 0)
        rendered.append(Text.assemble(Text(base_text, style=base_style), Text(spacer), overlay_line, Text(" " * right_margin)))

    return rendered


def build_history_label_line(label: str, percent: float, width: int, style: str) -> Text:
    """Render aligned history labels and dotted value rulers."""
    label_width = 12
    dot_width = max(width - label_width - 6, 8)
    return Text(f"{label:<{label_width}}{render_dots(percent, dot_width)} {percent:>3.0f}%", style=style)


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
    sorted_processes = sorted(
        list(processes),
        key=lambda process: (getattr(process, "used_memory_mb", None) or 0, getattr(process, "pid", 0)),
        reverse=True,
    )
    visible_processes = sorted_processes[: layout.process_rows]
    hidden_count = max(len(sorted_processes) - len(visible_processes), 0)
    header = "PID     USER        GPU MEM ↓   GPU %   POWER   TIME      COMMAND"
    lines = [Text(header, style=f"bold {BTOP_GREEN}")]

    if not visible_processes:
        lines.append(Text("No current-user GPU processes.", style=BTOP_MUTED))
    else:
        for process in visible_processes:
            pid = getattr(process, "pid", "?")
            username = truncate_text(getattr(process, "username", None) or "n/a", 10)
            process_name = getattr(process, "name", None) or "unknown"
            command_summary = getattr(process, "command_summary", None)
            label = command_summary if command_summary else process_name
            memory_label = format_process_memory(getattr(process, "used_memory_mb", None))
            if layout.show_command_summary:
                line = f"{pid:<7} {username:<10} {memory_label:>9}   {'n/a':>5}   {'n/a':>5}   {'n/a':>7}   {label}"
            else:
                line = f"{pid:<7} {username:<10} {memory_label:>9}   {label}"
            lines.append(Text(line, style=BTOP_TEXT))

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


class TopHeaderWidget(Static):
    """Compact dashboard header."""

    def __init__(self, refresh_interval: float = 0.7, backend_label: str = "n/a") -> None:
        super().__init__(id="top-header")
        self.refresh_interval = refresh_interval
        self.backend_label = backend_label
        self.selected_gpu = None
        self.gpu_count = 0
        self.dashboard_layout = resolve_gpu_dashboard_layout(120, 32)

    def on_mount(self) -> None:
        self.update_timer = self.set_interval(1.0, self.update_time)
        self.update_time()

    def update_snapshot(self, selected_gpu, gpu_count: int, backend_label: str, refresh_interval: float, layout: Optional[GPUDashboardLayout] = None) -> None:
        self.selected_gpu = selected_gpu
        self.gpu_count = gpu_count
        self.backend_label = backend_label
        self.refresh_interval = refresh_interval
        if layout is not None:
            self.dashboard_layout = layout
        self.update_time()

    def render_header(self, current_time: Optional[str] = None) -> Text:
        current_time = current_time or datetime.now().strftime("%H:%M:%S")
        width = self.dashboard_layout.total_width or getattr(getattr(self, "size", None), "width", 0) or 96
        refresh_label = f"{self.refresh_interval:.1f}".rstrip("0").rstrip(".") + "s"
        if self.dashboard_layout.density == "compact":
            right_options = [
                "[1-9] GPU [g] Charts [d] Detail [p] Proc [s] Graph [q] Quit",
                "[1-9] GPU [g] Charts [d] Detail [p] Proc [q] Quit",
                "[1-9] GPU [g/d/p] View [q] Quit",
            ]
        else:
            right_options = [
                "[1-9] Switch  [j/k] GPU  [s] Graph  [q] Quit",
                "[1-9] Switch  [j/k] GPU  [q] Quit",
                "[1-9] GPU  [q] Quit",
            ]
        fixed_prefix = "xtop    GPU: "
        gpu_id = "n/a" if self.selected_gpu is None else str(getattr(self.selected_gpu, "gpu_id", 0))
        gpu_name = "n/a" if self.selected_gpu is None else getattr(self.selected_gpu, "name", "unknown")
        fixed_middle = f"    | Backend: {self.backend_label} | Refresh: {refresh_label} | {current_time}"
        right = next((candidate for candidate in right_options if len(candidate) <= max(width // 3, 16)), right_options[-1])
        reserved = len(fixed_prefix) + len(gpu_id) + 3 + len(fixed_middle) + len(right) + 2
        name_width = max(8, width - reserved)
        selected_label = f"{fixed_prefix}{gpu_id} > {truncate_text(gpu_name, name_width)}"
        left = f"{selected_label}{fixed_middle}"
        available = max(width - len(left) - len(right), 1)
        line = f"{left}{' ' * available}{right}"
        return Text(truncate_text(line, width), style=f"bold {BTOP_TEXT}")

    def update_time(self) -> None:
        self.update(self.render_header())


class TimeWidget(TopHeaderWidget):
    """Backward-compatible header name."""


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
        self.power_history = deque([0.0] * 120, maxlen=120)
        self.temperature_history = deque([0.0] * 120, maxlen=120)
        self.graph_style = graph_style
        self.dashboard_layout = resolve_gpu_dashboard_layout(120, 32)

    def update_snapshot(
        self,
        gpu_stats,
        gpu_count,
        utilization_history,
        memory_history,
        graph_style,
        layout,
        gpus=None,
        power_history=None,
        temperature_history=None,
    ):
        self.gpu_stats = gpu_stats
        self.gpus = list(gpus or [])
        self.gpu_count = gpu_count
        self.utilization_history = utilization_history
        self.memory_history = memory_history
        self.power_history = power_history or self.power_history
        self.temperature_history = temperature_history or self.temperature_history
        self.graph_style = graph_style
        self.dashboard_layout = layout
        self.update(self.render_history())

    def render_history(self) -> RenderableType:
        if self.dashboard_layout.too_small:
            lines = [
                Text("Terminal too small for xtop GPU dashboard.", style=f"bold {BTOP_YELLOW}"),
                Text("Minimum size: 80x24", style=BTOP_TEXT),
                Text(f"Current size: {self.dashboard_layout.total_width}x{self.dashboard_layout.total_height}", style=BTOP_MUTED),
            ]
            return make_box("xtop", lines, self.dashboard_layout.body_width, BTOP_BORDER_YELLOW)

        if self.gpu_stats is None:
            return make_box("gpu", [Text("No GPU selected.", style=BTOP_YELLOW)], self.dashboard_layout.history_width, BTOP_BORDER_GREEN)

        if self.dashboard_layout.density == "compact":
            return self._render_compact_history()

        util_value = getattr(self.gpu_stats, "utilization", 0) or 0
        mem_used = getattr(self.gpu_stats, "memory_used", None)
        mem_total = getattr(self.gpu_stats, "memory_total", None)
        power_usage = getattr(self.gpu_stats, "power_usage", None) or 0
        power_limit = getattr(self.gpu_stats, "power_limit", None) or max(power_usage, 1)
        temperature = getattr(self.gpu_stats, "temperature", None) or 0
        chart_width = max(self.dashboard_layout.history_width - 4, 24)
        chart_height = self.dashboard_layout.history_height
        title_prefix = f"HISTORY  Selected GPU {self.gpu_stats.gpu_id} - "
        title_name_width = max(18, min(72, self.dashboard_layout.history_width - len(title_prefix) - 4))
        title = f"{title_prefix}{truncate_text(self.gpu_stats.name, title_name_width)}"

        lines = []
        lines.extend(
            build_metric_chart(
                "GPU UTILIZATION (%)",
                self.utilization_history,
                chart_width,
                chart_height,
                100.0,
                format_percent(util_value),
                ColorTheme.GPU_BLUE,
                self.graph_style,
                BTOP_CYAN,
            )
        )
        lines.extend(
            build_metric_chart(
                "MEMORY USED (GiB)",
                self.memory_history,
                chart_width,
                self.dashboard_layout.memory_graph_height,
                mem_total or 1.0,
                f"{format_memory_gib(mem_used)} / {format_memory_gib(mem_total)}",
                ColorTheme.GPU_YELLOW,
                self.graph_style,
                BTOP_YELLOW,
            )
        )
        lines.extend(
            build_metric_chart(
                "POWER DRAW (W)",
                self.power_history,
                chart_width,
                chart_height,
                power_limit,
                f"{power_usage:.0f} / {power_limit:.0f}",
                ColorTheme.NPU_MAGENTA,
                self.graph_style,
                BTOP_MAGENTA,
            )
        )
        temp_color = BTOP_GREEN if temperature < 75 else BTOP_ORANGE if temperature < 88 else BTOP_RED
        lines.extend(
            build_metric_chart(
                "TEMPERATURE (C)",
                self.temperature_history,
                chart_width,
                chart_height,
                100.0,
                format_na(temperature, "C"),
                ColorTheme.GPU_GREEN,
                self.graph_style,
                temp_color,
            )
        )
        return make_box(title, lines, self.dashboard_layout.history_width, BTOP_BORDER_GREEN)

    def _compact_chart_line(self, label: str, values, max_value: float, current_label: str, color: str) -> Text:
        content_width = max(self.dashboard_layout.body_width - 2, 20)
        label_width = 7
        value_width = min(max(len(current_label), 4), 14)
        spark_width = max(content_width - label_width - value_width - 2, 8)
        return Text.assemble(
            Text(f"{label:<{label_width}}", style=f"bold {color}"),
            Text(render_sparkline(values, spark_width, max_value), style=color),
            Text(f" {truncate_text(current_label, value_width):>{value_width}}", style=color),
        )

    def _render_compact_history(self) -> RenderableType:
        util_value = getattr(self.gpu_stats, "utilization", 0) or 0
        mem_used = getattr(self.gpu_stats, "memory_used", None)
        mem_total = getattr(self.gpu_stats, "memory_total", None)
        power_usage = getattr(self.gpu_stats, "power_usage", None) or 0
        power_limit = getattr(self.gpu_stats, "power_limit", None) or max(power_usage, 1)
        temperature = getattr(self.gpu_stats, "temperature", None) or 0
        temp_color = BTOP_GREEN if temperature < 75 else BTOP_ORANGE if temperature < 88 else BTOP_RED
        title = f"CHARTS  GPU {self.gpu_stats.gpu_id} - {truncate_text(self.gpu_stats.name, 18)}"
        lines = [
            self._compact_chart_line("UTIL", self.utilization_history, 100.0, format_percent(util_value), BTOP_CYAN),
            self._compact_chart_line("MEM", self.memory_history, mem_total or 1.0, f"{format_memory_gib(mem_used)}/{format_memory_gib(mem_total)}G", BTOP_YELLOW),
            self._compact_chart_line("PWR", self.power_history, power_limit, f"{power_usage:.0f}/{power_limit:.0f}W", BTOP_MAGENTA),
            self._compact_chart_line("TEMP", self.temperature_history, 100.0, format_na(temperature, "C"), temp_color),
        ]
        return make_box(title, lines, self.dashboard_layout.body_width, BTOP_BORDER_GREEN)


class GPUOverviewWidget(Static):
    """Fixed multi-GPU overview and switcher row."""

    def __init__(self) -> None:
        super().__init__(id="gpu-overview")
        self.gpus = []
        self.selected_gpu_id = 0
        self.utilization_history = {}
        self.dashboard_layout = resolve_gpu_dashboard_layout(120, 32)

    def update_snapshot(self, gpus, selected_gpu_id, layout, utilization_history=None):
        self.gpus = list(gpus)
        self.selected_gpu_id = selected_gpu_id
        self.utilization_history = utilization_history or {}
        self.dashboard_layout = layout
        self.update(self.render_overview())

    def _card_lines(self, gpu, card_width: int) -> list[Text]:
        content_width = max(card_width - 2, 20)
        gpu_id = getattr(gpu, "gpu_id", 0)
        selected = gpu_id == self.selected_gpu_id
        util = getattr(gpu, "utilization", None)
        mem_used = getattr(gpu, "memory_used", None)
        mem_total = getattr(gpu, "memory_total", None)
        mem_percent = calculate_memory_percent(gpu)
        power_usage = getattr(gpu, "power_usage", None)
        power_limit = getattr(gpu, "power_limit", None)
        power_percent = calculate_power_percent(gpu)
        temp = getattr(gpu, "temperature", None)
        fan = format_fan_summary(gpu, self.dashboard_layout.show_fan_rpm)
        history = self.utilization_history.get(gpu_id, deque([util or 0.0], maxlen=1))
        spark_width = max(content_width - 2, 8)
        bar_width = max(content_width - 10, 8)
        active_label = " ACTIVE" if selected else ""
        border_style = BTOP_CYAN if selected else BTOP_MUTED

        lines = [
            Text(
                f"{gpu_id:<2} {truncate_text(getattr(gpu, 'name', 'unknown'), content_width - 17)}{active_label:>8} {format_percent(util):>4}",
                style=f"bold {BTOP_CYAN if selected else BTOP_TEXT}",
            ),
            Text(render_sparkline(history, spark_width, 100.0), style=BTOP_CYAN),
            Text(f"Mem {format_memory_gib(mem_used):>5}/{format_memory_gib(mem_total):<5} GiB {format_percent(mem_percent):>5}", style=BTOP_YELLOW),
            Text(f"    {render_bar(mem_percent, bar_width)}", style=BTOP_YELLOW),
            Text(f"Pwr {format_na(power_usage, 'W'):>6} / {format_na(power_limit, 'W'):<6} {format_percent(power_percent):>5}", style=BTOP_MAGENTA),
            Text(f"    {render_bar(power_percent, bar_width)}", style=BTOP_MAGENTA),
            Text(f"Temp {format_na(temp, 'C'):<8} Fan {truncate_text(fan, max(content_width - 18, 3))}", style=BTOP_GREEN),
        ]
        return build_box_lines("", lines, card_width, border_style)

    def _compact_card_lines(self, gpu, card_width: int) -> list[Text]:
        content_width = max(card_width - 2, 20)
        gpu_id = getattr(gpu, "gpu_id", 0)
        selected = gpu_id == self.selected_gpu_id
        util = getattr(gpu, "utilization", None)
        mem_percent = calculate_memory_percent(gpu)
        power_percent = calculate_power_percent(gpu)
        temp = getattr(gpu, "temperature", None)
        history = self.utilization_history.get(gpu_id, deque([util or 0.0], maxlen=1))
        active_label = " ACTIVE" if selected else ""
        border_style = BTOP_CYAN if selected else BTOP_MUTED
        name_width = max(content_width - 18, 8)
        lines = [
            Text(
                f"{gpu_id:<2} {truncate_text(getattr(gpu, 'name', 'unknown'), name_width)}{active_label:>7} {format_percent(util):>4}",
                style=f"bold {BTOP_CYAN if selected else BTOP_TEXT}",
            ),
            Text(render_sparkline(history, max(content_width - 2, 8), 100.0), style=BTOP_CYAN),
            Text(
                f"Mem {format_percent(mem_percent):>4}  Pwr {format_percent(power_percent):>4}  Temp {format_na(temp, 'C'):>4}",
                style=BTOP_TEXT,
            ),
        ]
        return build_box_lines("", lines, card_width, border_style)

    def render_overview(self) -> RenderableType:
        if not self.gpus:
            return make_box("OVERVIEW  GPU SWITCHER", [Text("No GPUs detected.", style=BTOP_MUTED)], self.dashboard_layout.overview_width, BTOP_BORDER_GREEN)

        content_width = max(self.dashboard_layout.overview_width - 2, 20)
        if self.dashboard_layout.overview_compact:
            max_cards = max(1, min(self.dashboard_layout.overview_card_count, len(self.gpus)))
            card_width = max(28, (content_width - max_cards + 1) // max_cards)
        else:
            card_width = min(self.dashboard_layout.meter_width, max(28, content_width // max(min(len(self.gpus), 4), 1) - 1))
            max_cards = max(1, min(self.dashboard_layout.overview_card_count or 4, content_width // (card_width + 1)))
        selected_position = next((index for index, gpu in enumerate(self.gpus) if getattr(gpu, "gpu_id", None) == self.selected_gpu_id), 0)
        start = max(0, min(selected_position - max_cards // 2, len(self.gpus) - max_cards))
        visible_gpus = self.gpus[start : start + max_cards]
        if self.dashboard_layout.overview_compact:
            rendered_cards = [self._compact_card_lines(gpu, card_width) for gpu in visible_gpus]
        else:
            rendered_cards = [self._card_lines(gpu, card_width) for gpu in visible_gpus]
        row_count = max(len(card) for card in rendered_cards)
        rows = []
        for row_index in range(row_count):
            parts = []
            for card in rendered_cards:
                part = card[row_index] if row_index < len(card) else Text(" " * card_width)
                parts.append(part)
                parts.append(Text(" "))
            rows.append(Text.assemble(*parts))
        if start > 0:
            rows[0] = Text.assemble(Text("< ", style=BTOP_MUTED), rows[0])
        if start + len(visible_gpus) < len(self.gpus):
            rows[0] = Text.assemble(rows[0], Text(" >", style=BTOP_MUTED))
        return make_box("OVERVIEW  GPU SWITCHER  (press number to switch)", rows, self.dashboard_layout.overview_width, BTOP_BORDER_GREEN)

    def render_meters(self) -> RenderableType:
        """Backward-compatible render method."""
        return self.render_overview()


class GPUMeterWidget(GPUOverviewWidget):
    """Backward-compatible name for the GPU overview panel."""


class SelectedGPUDetailPanel(Static):
    """Right-side selected GPU details."""

    def __init__(self) -> None:
        super().__init__(id="gpu-details")
        self.gpu_stats = None
        self.dashboard_layout = resolve_gpu_dashboard_layout(120, 32)
        self.pcie_rx_history = deque([0.0] * 120, maxlen=120)
        self.pcie_tx_history = deque([0.0] * 120, maxlen=120)

    def update_snapshot(self, gpu_stats, layout, pcie_rx_history=None, pcie_tx_history=None):
        self.gpu_stats = gpu_stats
        self.dashboard_layout = layout
        self.pcie_rx_history = pcie_rx_history or self.pcie_rx_history
        self.pcie_tx_history = pcie_tx_history or self.pcie_tx_history
        self.update(self.render_detail())

    def _content_width(self) -> int:
        return max(self.dashboard_layout.detail_width - 2, 24)

    def _separator(self) -> Text:
        return Text("─" * max(self._content_width() - 2, 12), style=BTOP_MUTED)

    def _pair_line(self, label: str, value: str, value_style: str = BTOP_TEXT) -> Text:
        label_width = 18
        value_width = max(self._content_width() - label_width, 8)
        return Text.assemble(
            Text(f"{label:<{label_width}}", style=BTOP_MUTED),
            Text(truncate_text(value, value_width), style=value_style),
        )

    def _bar_line(self, label: str, value: str, percent: Optional[float], color: str, show_percent: bool = True) -> Text:
        content_width = max(self._content_width() - 2, 22)
        label_width = 16 if "Clock" in label else 12
        percent_label = format_percent(percent) if show_percent else ""
        percent_width = 5 if show_percent else 0
        value_width = max(8, min(18, content_width - label_width - percent_width - 7))
        bar_width = max(4, content_width - label_width - value_width - percent_width - 1)
        value_text = truncate_text(value, value_width)
        bar = render_bar(percent or 0.0, bar_width)
        return Text.assemble(
            Text(f"{label:<{label_width}}", style=color),
            Text(f"{value_text:<{value_width}} ", style=color),
            Text(bar, style=color),
            Text(f" {percent_label:>4}" if show_percent else "", style=color),
        )

    def _pcie_line(self, label: str, value: str, throughput_kbps: Optional[int], history) -> Text:
        content_width = max(self._content_width() - 2, 22)
        label_width = 18
        value_width = 14
        spark_width = max(content_width - label_width - value_width, 0)
        sparkline = ""
        if throughput_kbps is not None and spark_width >= 6:
            history_values = list(history)[-spark_width:] if history is not None else [throughput_kbps]
            sparkline = render_sparkline(history_values, spark_width, max(max(history_values or [0]), throughput_kbps, 1))
        return Text.assemble(
            Text(f"{label:<{label_width}}", style=BTOP_MUTED),
            Text(f"{truncate_text(value, value_width):<{value_width}}", style=BTOP_TEXT),
            Text(sparkline, style=BTOP_CYAN),
        )

    def _target_content_height(self) -> int:
        chart_rows = (
            self.dashboard_layout.history_height * 3
            + self.dashboard_layout.memory_graph_height
            + 4
        )
        process_rows = self.dashboard_layout.process_rows + 1
        return chart_rows + process_rows + 2

    def render_detail(self) -> RenderableType:
        if self.gpu_stats is None:
            return make_box("SELECTED GPU", [Text("No GPU selected.", style=BTOP_YELLOW)], self.dashboard_layout.detail_width, BTOP_BORDER_GREEN)

        mem_used = getattr(self.gpu_stats, "memory_used", None)
        mem_total = getattr(self.gpu_stats, "memory_total", None)
        mem_percent = calculate_memory_percent(self.gpu_stats)
        power_usage = getattr(self.gpu_stats, "power_usage", None)
        power_limit = getattr(self.gpu_stats, "power_limit", None)
        power_percent = calculate_power_percent(self.gpu_stats)
        temp = getattr(self.gpu_stats, "temperature", None)
        temp_percent = min(max(temp or 0, 0), 100)
        fan_percent = getattr(self.gpu_stats, "fan_speed", None)
        fan_rpm = getattr(self.gpu_stats, "fan_speed_rpm", None)
        fan_value = f"{fan_rpm} RPM" if fan_rpm is not None else format_fan_summary(self.gpu_stats, False)
        graphics_clock = getattr(self.gpu_stats, "graphics_clock_mhz", None)
        memory_clock = getattr(self.gpu_stats, "memory_clock_mhz", None)
        sm_clock = getattr(self.gpu_stats, "sm_clock_mhz", None)
        pcie_rx = getattr(self.gpu_stats, "pcie_rx_kbps", None)
        pcie_tx = getattr(self.gpu_stats, "pcie_tx_kbps", None)
        health = "OK" if temp is None or temp < 80 else "WARN" if temp < 90 else "HOT"
        health_style = BTOP_GREEN if health == "OK" else BTOP_ORANGE if health == "WARN" else BTOP_RED

        lines = [
            self._pair_line("Name", getattr(self.gpu_stats, "name", "unknown")),
            self._pair_line("GPU Index", str(getattr(self.gpu_stats, "gpu_id", "n/a"))),
            self._pair_line("UUID", getattr(self.gpu_stats, "uuid", None) or "n/a"),
            self._pair_line("State", "Active", BTOP_GREEN),
            self._pair_line("Driver", f"{getattr(self.gpu_stats, 'driver_version', 'n/a')}    CUDA {getattr(self.gpu_stats, 'cuda_version', 'n/a')}"),
            self._pair_line("Health", health, health_style),
            self._separator(),
            self._bar_line("Memory", f"{format_memory_gib(mem_used)} / {format_memory_gib(mem_total)} GiB", mem_percent, BTOP_YELLOW),
            self._bar_line("Power", f"{format_na(power_usage, 'W')} / {format_na(power_limit, 'W')}", power_percent, BTOP_MAGENTA),
            self._bar_line("Temp", format_na(temp, "C"), temp_percent, BTOP_GREEN if (temp or 0) < 80 else BTOP_ORANGE),
            self._bar_line("Fan", fan_value, fan_percent, BTOP_GREEN),
            self._separator(),
            self._bar_line("Graphics Clock", format_na(graphics_clock, " MHz"), (graphics_clock or 0) / 3000 * 100, BTOP_CYAN, False),
            self._bar_line("Memory Clock", format_na(memory_clock, " MHz"), (memory_clock or 0) / 12000 * 100, BTOP_CYAN, False),
            self._bar_line("SM Clock", format_na(sm_clock, " MHz"), (sm_clock or 0) / 3000 * 100, BTOP_CYAN, False),
            self._separator(),
            self._pcie_line("PCIe RX", format_data_rate(pcie_rx).replace("N/A", "n/a"), pcie_rx, self.pcie_rx_history),
            self._pcie_line("PCIe TX", format_data_rate(pcie_tx).replace("N/A", "n/a"), pcie_tx, self.pcie_tx_history),
            self._pair_line("PCIe Gen", getattr(self.gpu_stats, "pcie_gen", None) or "n/a"),
            self._pair_line("Link Width", getattr(self.gpu_stats, "pcie_link_width", None) or "n/a"),
            self._pair_line("Link State", "Active" if pcie_rx is not None or pcie_tx is not None else "n/a", BTOP_GREEN if pcie_rx is not None or pcie_tx is not None else BTOP_MUTED),
            self._separator(),
            self._pair_line("Processes", str(len(getattr(self.gpu_stats, "processes", [])))),
            self._pair_line("Compute Clients", str(len(getattr(self.gpu_stats, "processes", [])))),
            self._pair_line("Uptime", getattr(self.gpu_stats, "uptime", None) or "n/a"),
            self._pair_line("ECC Errors", str(getattr(self.gpu_stats, "ecc_errors", 0) if getattr(self.gpu_stats, "ecc_errors", None) is not None else "n/a")),
            self._pair_line("Performance Cap", getattr(self.gpu_stats, "performance_cap", None) or "None"),
        ]
        if self.dashboard_layout.density in {"wide", "normal"}:
            while len(lines) < self._target_content_height():
                lines.append(Text(""))
        return make_box("SELECTED GPU", lines, self.dashboard_layout.detail_width, BTOP_BORDER_GREEN)

    def render_resources(self) -> RenderableType:
        """Backward-compatible render method."""
        return self.render_detail()


class GPUResourceWidget(SelectedGPUDetailPanel):
    """Backward-compatible selected GPU detail panel name."""


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
        return make_box("PROCESSES on selected GPU", build_process_panel_lines(self.processes, self.dashboard_layout), self.dashboard_layout.process_width, BTOP_BORDER_GREEN)


class GPUProcessPanel(GPUProcessWidget):
    """Primary process panel name."""


class StatusLineWidget(Static):
    """Bottom one-line diagnostic status."""

    def __init__(self) -> None:
        super().__init__(id="gpu-status")
        self.gpu_stats = None
        self.status_messages = []
        self.dashboard_layout = resolve_gpu_dashboard_layout(120, 32)
        self.backend_label = "n/a"

    def update_snapshot(self, gpu_stats, status_messages, layout, backend_label: str = "n/a"):
        self.gpu_stats = gpu_stats
        self.status_messages = list(status_messages)
        self.dashboard_layout = layout
        self.backend_label = backend_label
        self.update(self.render_status())

    def render_status(self) -> RenderableType:
        if self.gpu_stats is None:
            return Text("STATUS  No GPU selected.", style=BTOP_YELLOW)

        host = socket.gethostname().split(".")[0] or "n/a"
        warnings = len(self.status_messages)
        parts = [
            f"STATUS  Backend: {self.backend_label}",
            f"Host: {host}",
            f"Driver {getattr(self.gpu_stats, 'driver_version', 'N/A')}",
            f"CUDA {getattr(self.gpu_stats, 'cuda_version', 'N/A')}",
            f"Python env: {'active' if os.environ.get('VIRTUAL_ENV') or os.environ.get('CONDA_PREFIX') else 'n/a'}",
        ]
        if self.status_messages:
            parts.extend(self.status_messages)
        parts.append("No Warnings" if warnings == 0 else f"Warnings: {warnings}")
        return Text(truncate_text(" | ".join(parts), self.dashboard_layout.status_width), style=BTOP_TEXT)


class GPUStatusWidget(StatusLineWidget):
    """Backward-compatible status widget name."""


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
