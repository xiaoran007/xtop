from collections import deque

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Footer, Header

from xtop.xtopUtil import getOS

from .tui_backends import (
    build_status_messages,
    load_gpu_backend,
    load_npu_backend,
    resolve_gpu_unavailable_message,
    resolve_npu_unavailable_message,
)
from .tui_graphs import GraphStyle
from .tui_layout import resolve_gpu_dashboard_layout
from .tui_widgets import GPUDetailWidget, GPUOverviewWidget, GPUProcessWidget, StatusWidget, TimeWidget, calculate_memory_percent


class XtopTUI(App):
    """Textual app for xtop hardware monitoring."""

    CSS = """
    Screen {
        layout: vertical;
    }

    #time-widget {
        height: 1;
        padding: 0 1;
    }

    #main-container {
        height: 1fr;
        padding: 0 1 1 1;
    }

    #gpu-dashboard {
        height: auto;
        min-height: 24;
        width: 100%;
    }

    #gpu-left-column {
        min-width: 32;
        padding: 0 1 0 0;
    }

    #gpu-right-column {
        width: 1fr;
    }

    #gpu-overview,
    #gpu-processes,
    #gpu-detail {
        width: 100%;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("s", "toggle_graph_style", "Graph Style"),
        ("j", "select_next_gpu", "Next GPU"),
        ("down", "select_next_gpu", "Next GPU"),
        ("k", "select_previous_gpu", "Previous GPU"),
        ("up", "select_previous_gpu", "Previous GPU"),
        ("ctrl+t", "toggle_dark", "Toggle Dark/Light Mode"),
    ]

    def __init__(
        self,
        enable_gpu: bool = True,
        enable_cpu: bool = True,
        enable_npu: bool = False,
        use_mock_gpu: bool = False,
    ):
        super().__init__()
        self.os_name = getOS()
        self.enable_gpu = enable_gpu
        self.enable_cpu = enable_cpu
        self.enable_npu = enable_npu
        self.use_mock_gpu = use_mock_gpu
        self.status_messages = []

        gpu_error = None
        npu_error = None

        if enable_gpu:
            self.gpu_backend, gpu_error = load_gpu_backend(use_mock=use_mock_gpu)
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

        if self.use_mock_gpu:
            self.status_messages.append("Using simulated Nvidia GPU data for TUI development.")

        self.has_gpu = False
        self.has_cpu = False
        self.has_npu = False
        self.graph_style = GraphStyle.BRAILLE
        self.selected_gpu_index = 0
        self.utilization_history = {}
        self.memory_history = {}
        self.gpu_left_column = None
        self.gpu_right_column = None
        self.gpu_overview_widget = None
        self.gpu_process_widget = None
        self.gpu_detail_widget = None

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        yield TimeWidget(id="time-widget")
        yield VerticalScroll(id="main-container")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize backends and mount available dashboards."""
        container = self.query_one("#main-container")
        has_any_hardware = False

        if self.enable_cpu:
            self.has_cpu = False

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

        if self.has_gpu:
            has_any_hardware = True
            self.gpu_backend.update()
            self._record_gpu_histories()
            dashboard = Horizontal(id="gpu-dashboard")
            self.gpu_left_column = Vertical(id="gpu-left-column")
            self.gpu_right_column = Vertical(id="gpu-right-column")
            self.gpu_overview_widget = GPUOverviewWidget()
            self.gpu_process_widget = GPUProcessWidget()
            self.gpu_detail_widget = GPUDetailWidget(self.graph_style)
            container.mount(dashboard)
            dashboard.mount(self.gpu_left_column)
            dashboard.mount(self.gpu_right_column)
            self.gpu_left_column.mount(self.gpu_overview_widget)
            self.gpu_left_column.mount(self.gpu_process_widget)
            self.gpu_right_column.mount(self.gpu_detail_widget)
            self._refresh_gpu_widgets()

        for message in dict.fromkeys(self.status_messages):
            container.mount(StatusWidget(message))

        if has_any_hardware:
            self.update_timer = self.set_interval(0.7, self.update_data)
        elif not self.status_messages:
            container.mount(StatusWidget("No requested hardware monitors are available."))

    def on_unmount(self) -> None:
        """Shutdown initialized backends."""
        if self.has_cpu:
            self.cpu_backend.shutdown()
        if self.has_gpu:
            self.gpu_backend.shutdown()
        if self.has_npu:
            self.npu_backend.shutdown()

    def action_toggle_graph_style(self) -> None:
        """Toggle between block and braille graph styles."""
        self.graph_style = GraphStyle.BLOCK if self.graph_style == GraphStyle.BRAILLE else GraphStyle.BRAILLE
        self._refresh_gpu_widgets()

    def action_select_next_gpu(self) -> None:
        """Select the next GPU in the overview."""
        if not self.has_gpu:
            return
        self.selected_gpu_index = (self.selected_gpu_index + 1) % self.gpu_backend.gpu_number
        self._refresh_gpu_widgets()

    def action_select_previous_gpu(self) -> None:
        """Select the previous GPU in the overview."""
        if not self.has_gpu:
            return
        self.selected_gpu_index = (self.selected_gpu_index - 1) % self.gpu_backend.gpu_number
        self._refresh_gpu_widgets()

    def update_data(self) -> None:
        """Update backend data and refresh mounted widgets."""
        if self.has_cpu:
            self.cpu_backend.update()
        if self.has_gpu:
            self.gpu_backend.update()
            self._record_gpu_histories()
            self._refresh_gpu_widgets()
        if self.has_npu:
            self.npu_backend.update()

    def _selected_gpu(self):
        if not self.has_gpu or not self.gpu_backend.gpus:
            return None
        self.selected_gpu_index = max(0, min(self.selected_gpu_index, len(self.gpu_backend.gpus) - 1))
        return self.gpu_backend.gpus[self.selected_gpu_index]

    def _record_gpu_histories(self) -> None:
        for gpu in self.gpu_backend.gpus:
            util_history = self.utilization_history.setdefault(gpu.gpu_id, deque([0.0] * 120, maxlen=120))
            memory_history = self.memory_history.setdefault(gpu.gpu_id, deque([0.0] * 120, maxlen=120))
            util_history.append(getattr(gpu, "utilization", 0) or 0.0)
            memory_history.append(calculate_memory_percent(gpu))

    def _refresh_gpu_widgets(self) -> None:
        if self.gpu_overview_widget is None or self.gpu_process_widget is None or self.gpu_detail_widget is None:
            return

        selected_gpu = self._selected_gpu()
        if selected_gpu is None:
            return

        layout = self._resolve_dashboard_layout()
        self._apply_dashboard_layout(layout)
        self.gpu_overview_widget.update_snapshot(self.gpu_backend.gpus, selected_gpu.gpu_id, layout)
        self.gpu_process_widget.update_snapshot(selected_gpu, layout)
        self.gpu_detail_widget.update_snapshot(
            selected_gpu,
            self.utilization_history[selected_gpu.gpu_id],
            self.memory_history[selected_gpu.gpu_id],
            self.graph_style,
            layout,
        )

    def _resolve_dashboard_layout(self):
        size = getattr(self, "size", None)
        try:
            screen = getattr(self, "screen", None)
        except Exception:
            screen = None
        screen_size = getattr(screen, "size", None)
        width = getattr(size, "width", 0) or getattr(screen_size, "width", 0) or 120
        height = getattr(size, "height", 0) or getattr(screen_size, "height", 0) or 32
        return resolve_gpu_dashboard_layout(width, height)

    def _apply_dashboard_layout(self, layout) -> None:
        if self.gpu_left_column is not None:
            self.gpu_left_column.styles.width = layout.left_width
        if self.gpu_right_column is not None:
            self.gpu_right_column.styles.width = layout.right_width
