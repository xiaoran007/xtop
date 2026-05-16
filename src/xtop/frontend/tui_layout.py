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
    mode: str
    total_width: int
    total_height: int
    history_width: int
    history_height: int
    meter_width: int
    resource_width: int
    process_width: int
    process_rows: int
    status_width: int
    graph_width: int
    memory_graph_height: int
    meter_bar_width: int
    resource_bar_width: int
    process_limit: int
    show_command_summary: bool
    show_extended_metrics: bool
    show_driver_info: bool
    show_pcie: bool
    show_fan_rpm: bool
    compact: bool
    overview_width: int
    detail_width: int
    graph_height: int
    left_width: int
    right_width: int
    overview_bar_width: int
    utilization_graph_height: int


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
    """Choose a single-card layout for compatibility renderers."""
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
    """Choose btop-style dashboard regions from the terminal size."""
    total_width = max(width, 72)
    total_height = max(height, 22)

    if total_width >= 160:
        mode = "wide"
        meter_width = min(62, max(50, total_width // 3))
        history_width = total_width
        resource_width = min(max(total_width // 3, 48), 70)
        process_width = max(total_width - resource_width - 3, 52)
        show_command_summary = True
        show_extended_metrics = True
        show_pcie = True
        show_fan_rpm = True
    elif total_width >= 100:
        mode = "normal"
        meter_width = min(48, max(38, total_width // 3))
        history_width = total_width
        resource_width = min(max(total_width // 3, 38), 52)
        process_width = max(total_width - resource_width - 3, 44)
        show_command_summary = total_width >= 128
        show_extended_metrics = total_width >= 116
        show_pcie = total_width >= 124
        show_fan_rpm = total_width >= 112
    else:
        mode = "narrow"
        meter_width = total_width
        history_width = total_width
        resource_width = total_width
        process_width = total_width
        show_command_summary = False
        show_extended_metrics = False
        show_pcie = False
        show_fan_rpm = False

    if total_height >= 42:
        history_height = 14
        memory_graph_height = 5
        process_rows = 10
    elif total_height >= 34:
        history_height = 11
        memory_graph_height = 4
        process_rows = 8
    elif total_height >= 28:
        history_height = 9
        memory_graph_height = 3
        process_rows = 6
    else:
        history_height = 7
        memory_graph_height = 3
        process_rows = 4

    if mode == "narrow":
        process_rows = max(3, min(process_rows, 5))

    graph_width = max(history_width - 4, 24)
    meter_bar_width = max(8, min(18, meter_width - 34))
    resource_bar_width = max(10, min(32, resource_width - 24))

    return GPUDashboardLayout(
        mode=mode,
        total_width=total_width,
        total_height=total_height,
        history_width=history_width,
        history_height=history_height,
        meter_width=meter_width,
        resource_width=resource_width,
        process_width=process_width,
        process_rows=process_rows,
        status_width=total_width,
        graph_width=graph_width,
        memory_graph_height=memory_graph_height,
        meter_bar_width=meter_bar_width,
        resource_bar_width=resource_bar_width,
        process_limit=process_rows,
        show_command_summary=show_command_summary,
        show_extended_metrics=show_extended_metrics,
        show_driver_info=total_width >= 100,
        show_pcie=show_pcie,
        show_fan_rpm=show_fan_rpm,
        compact=mode == "narrow",
        overview_width=meter_width,
        detail_width=history_width,
        graph_height=history_height,
        left_width=resource_width,
        right_width=process_width,
        overview_bar_width=meter_bar_width,
        utilization_graph_height=history_height,
    )
