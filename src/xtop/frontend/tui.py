"""Compatibility exports for the Textual xtop UI."""

from .tui_app import XtopTUI
from .tui_backends import (
    build_status_messages,
    load_gpu_backend,
    load_npu_backend,
    resolve_cpu_status_message,
    resolve_gpu_unavailable_message,
    resolve_npu_unavailable_message,
)
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
from .tui_widgets import (
    CPUStatsWidget,
    GPUDetailWidget,
    GPUOverviewWidget,
    GPUProcessWidget,
    GPUStatsWidget,
    NPUStatsWidget,
    StatusWidget,
    TimeWidget,
    build_process_lines,
    build_process_panel_lines,
    build_separator,
    make_widget_line,
    resolve_terminal_height,
)


__all__ = [
    "XtopTUI",
    "build_status_messages",
    "load_gpu_backend",
    "load_npu_backend",
    "resolve_cpu_status_message",
    "resolve_gpu_unavailable_message",
    "resolve_npu_unavailable_message",
    "ColorTheme",
    "GraphStyle",
    "create_graph",
    "GPUDashboardLayout",
    "GPUWidgetLayout",
    "format_data_rate",
    "format_optional_number",
    "format_process_memory",
    "resolve_gpu_dashboard_layout",
    "resolve_gpu_widget_layout",
    "truncate_text",
    "CPUStatsWidget",
    "GPUDetailWidget",
    "GPUOverviewWidget",
    "GPUProcessWidget",
    "GPUStatsWidget",
    "NPUStatsWidget",
    "StatusWidget",
    "TimeWidget",
    "build_process_lines",
    "build_process_panel_lines",
    "build_separator",
    "make_widget_line",
    "resolve_terminal_height",
]
