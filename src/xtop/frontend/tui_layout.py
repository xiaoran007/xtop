from dataclasses import dataclass
from typing import Optional


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


@dataclass
class GPUDashboardLayout:
    overview_width: int
    detail_width: int
    graph_width: int
    graph_height: int
    process_limit: int
    show_extended_metrics: bool
    show_command_summary: bool
    compact: bool
    left_width: int
    right_width: int
    overview_bar_width: int
    utilization_graph_height: int
    memory_graph_height: int
    show_driver_info: bool


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


def format_process_memory(memory_mb: Optional[float]) -> str:
    """Format per-process GPU memory usage."""
    if memory_mb is None:
        return "N/A"
    if memory_mb >= 1024:
        return f"{memory_mb / 1024:.1f}G"
    return f"{memory_mb:.0f}M"


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

    return GPUWidgetLayout(
        content_width=content_width,
        graph_width=max(content_width - 1, 24),
        graph_height=graph_height,
        process_limit=process_limit,
        show_driver_info=show_driver_info,
        show_extended_metrics=show_extended_metrics,
        show_command_summary=show_command_summary,
        show_graph=show_graph,
        compact_process_rows=compact,
    )


def resolve_gpu_dashboard_layout(width: int, height: int) -> GPUDashboardLayout:
    """Choose dashboard dimensions from the full terminal size."""
    terminal_width = max(width, 72)
    terminal_height = max(height, 20)
    compact = terminal_width < 104

    if terminal_width < 96:
        left_width = 34
    elif terminal_width < 132:
        left_width = 44
    elif terminal_width < 176:
        left_width = 54
    else:
        left_width = min(66, max(58, terminal_width // 3))

    right_width = max(terminal_width - left_width - 4, 40)

    utilization_graph_height = 6
    if terminal_height >= 42:
        utilization_graph_height = 12
    elif terminal_height >= 34:
        utilization_graph_height = 10
    elif terminal_height >= 28:
        utilization_graph_height = 8

    memory_graph_height = max(4, utilization_graph_height // 2)

    if terminal_height >= 40:
        process_limit = 8
    elif terminal_height >= 32:
        process_limit = 6
    elif terminal_height >= 26:
        process_limit = 4
    else:
        process_limit = 3

    return GPUDashboardLayout(
        overview_width=left_width,
        detail_width=right_width,
        graph_width=max(right_width - 4, 24),
        graph_height=utilization_graph_height,
        process_limit=process_limit,
        show_extended_metrics=right_width >= 72,
        show_command_summary=left_width >= 52,
        compact=compact,
        left_width=left_width,
        right_width=right_width,
        overview_bar_width=max(6, min(22, left_width - 30)),
        utilization_graph_height=utilization_graph_height,
        memory_graph_height=memory_graph_height,
        show_driver_info=right_width >= 62,
    )
