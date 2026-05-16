from collections import deque

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll

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
from .tui_widgets import (
    GPUHistoryWidget,
    GPUOverviewWidget,
    GPUProcessPanel,
    SelectedGPUDetailPanel,
    StatusLineWidget,
    StatusWidget,
    TopHeaderWidget,
)


class XtopTUI(App):
    """Textual app for xtop hardware monitoring."""

    CSS = """
    Screen {
        layout: vertical;
        background: #000000;
        color: #d7d7d7;
    }

    #top-header {
        height: 1;
        padding: 0 0;
        background: #000000;
        color: #d7d7d7;
        text-style: bold;
    }

    #main-container {
        height: 1fr;
        padding: 0 0 0 0;
        background: #000000;
    }

    #gpu-dashboard {
        width: 100%;
        background: #000000;
    }

    #gpu-overview-row,
    #gpu-main-row,
    #gpu-left-column,
    #gpu-status-row {
        width: 100%;
        height: auto;
        background: #000000;
    }

    #gpu-history,
    #gpu-overview,
    #gpu-details,
    #gpu-processes,
    #gpu-status {
        width: 100%;
        background: #000000;
        color: #d7d7d7;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("s", "toggle_graph_style", "Graph Style"),
        ("j", "select_next_gpu", "Next GPU"),
        ("right", "select_next_gpu", "Next GPU"),
        ("down", "select_next_gpu", "Next GPU"),
        ("k", "select_previous_gpu", "Previous GPU"),
        ("left", "select_previous_gpu", "Previous GPU"),
        ("up", "select_previous_gpu", "Previous GPU"),
        ("r", "refresh_now", "Refresh Now"),
        ("1", "select_gpu_1", "GPU 1"),
        ("2", "select_gpu_2", "GPU 2"),
        ("3", "select_gpu_3", "GPU 3"),
        ("4", "select_gpu_4", "GPU 4"),
        ("5", "select_gpu_5", "GPU 5"),
        ("6", "select_gpu_6", "GPU 6"),
        ("7", "select_gpu_7", "GPU 7"),
        ("8", "select_gpu_8", "GPU 8"),
        ("9", "select_gpu_9", "GPU 9"),
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
        self.power_history = {}
        self.temperature_history = {}
        self.top_header_widget = None
        self.gpu_overview_row = None
        self.gpu_main_row = None
        self.gpu_left_column = None
        self.gpu_status_row = None
        self.gpu_overview_widget = None
        self.gpu_history_widget = None
        self.gpu_detail_widget = None
        self.gpu_process_widget = None
        self.gpu_status_widget = None
        self.refresh_interval = 0.7

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        self.top_header_widget = TopHeaderWidget(refresh_interval=self.refresh_interval)
        yield self.top_header_widget
        yield VerticalScroll(id="main-container")

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
            dashboard = Vertical(id="gpu-dashboard")
            self.gpu_overview_row = Horizontal(id="gpu-overview-row")
            self.gpu_main_row = Horizontal(id="gpu-main-row")
            self.gpu_left_column = Vertical(id="gpu-left-column")
            self.gpu_status_row = Horizontal(id="gpu-status-row")
            self.gpu_overview_widget = GPUOverviewWidget()
            self.gpu_history_widget = GPUHistoryWidget(self.graph_style)
            self.gpu_detail_widget = SelectedGPUDetailPanel()
            self.gpu_process_widget = GPUProcessPanel()
            self.gpu_status_widget = StatusLineWidget()

            container.mount(dashboard)
            dashboard.mount(self.gpu_overview_row)
            dashboard.mount(self.gpu_main_row)
            dashboard.mount(self.gpu_status_row)
            self.gpu_overview_row.mount(self.gpu_overview_widget)
            self.gpu_main_row.mount(self.gpu_left_column)
            self.gpu_main_row.mount(self.gpu_detail_widget)
            self.gpu_left_column.mount(self.gpu_history_widget)
            self.gpu_left_column.mount(self.gpu_process_widget)
            self.gpu_status_row.mount(self.gpu_status_widget)
            self._refresh_gpu_widgets()

        if not self.has_gpu:
            for message in dict.fromkeys(self.status_messages):
                container.mount(StatusWidget(message))

        if has_any_hardware:
            self.update_timer = self.set_interval(self.refresh_interval, self.update_data)
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

    def action_refresh_now(self) -> None:
        """Refresh backend data immediately."""
        self.update_data()

    def _select_gpu_number(self, number: int) -> None:
        if not self.has_gpu:
            return
        target_index = number - 1
        if target_index < self.gpu_backend.gpu_number:
            self.selected_gpu_index = target_index
            self._refresh_gpu_widgets()

    def action_select_gpu_1(self) -> None:
        self._select_gpu_number(1)

    def action_select_gpu_2(self) -> None:
        self._select_gpu_number(2)

    def action_select_gpu_3(self) -> None:
        self._select_gpu_number(3)

    def action_select_gpu_4(self) -> None:
        self._select_gpu_number(4)

    def action_select_gpu_5(self) -> None:
        self._select_gpu_number(5)

    def action_select_gpu_6(self) -> None:
        self._select_gpu_number(6)

    def action_select_gpu_7(self) -> None:
        self._select_gpu_number(7)

    def action_select_gpu_8(self) -> None:
        self._select_gpu_number(8)

    def action_select_gpu_9(self) -> None:
        self._select_gpu_number(9)

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
            util_history = self.utilization_history.setdefault(gpu.gpu_id, deque([0.0] * 160, maxlen=160))
            memory_history = self.memory_history.setdefault(gpu.gpu_id, deque([0.0] * 160, maxlen=160))
            power_history = self.power_history.setdefault(gpu.gpu_id, deque([0.0] * 160, maxlen=160))
            temperature_history = self.temperature_history.setdefault(gpu.gpu_id, deque([0.0] * 160, maxlen=160))
            util_history.append(getattr(gpu, "utilization", 0) or 0.0)
            memory_history.append(getattr(gpu, "memory_used", 0) or 0.0)
            power_history.append(getattr(gpu, "power_usage", 0) or 0.0)
            temperature_history.append(getattr(gpu, "temperature", 0) or 0.0)

    def _refresh_gpu_widgets(self) -> None:
        required_widgets = [
            self.top_header_widget,
            self.gpu_overview_widget,
            self.gpu_history_widget,
            self.gpu_detail_widget,
            self.gpu_process_widget,
            self.gpu_status_widget,
        ]
        if any(widget is None for widget in required_widgets):
            return

        selected_gpu = self._selected_gpu()
        if selected_gpu is None:
            return

        layout = self._resolve_dashboard_layout()
        self._apply_dashboard_layout(layout)
        backend_label = self._gpu_backend_label()
        self.top_header_widget.update_snapshot(selected_gpu, len(self.gpu_backend.gpus), backend_label, self.refresh_interval)
        self.gpu_overview_widget.update_snapshot(self.gpu_backend.gpus, selected_gpu.gpu_id, layout, self.utilization_history)
        self.gpu_history_widget.update_snapshot(
            selected_gpu,
            len(self.gpu_backend.gpus),
            self.utilization_history[selected_gpu.gpu_id],
            self.memory_history[selected_gpu.gpu_id],
            self.graph_style,
            layout,
            self.gpu_backend.gpus,
            self.power_history[selected_gpu.gpu_id],
            self.temperature_history[selected_gpu.gpu_id],
        )
        self.gpu_detail_widget.update_snapshot(selected_gpu, layout)
        self.gpu_process_widget.update_snapshot(selected_gpu, layout)
        self.gpu_status_widget.update_snapshot(selected_gpu, self.status_messages, layout, backend_label)

    def _gpu_backend_label(self) -> str:
        if self.use_mock_gpu:
            return "Mock"
        if self.gpu_backend is None:
            return "n/a"
        name = self.gpu_backend.__class__.__name__
        if name == "NvidiaGPU":
            return "NVML"
        if name == "JetsonGPU":
            return "Jetson"
        return name

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
        main_layout = "vertical" if layout.mode == "narrow" else "horizontal"
        if self.gpu_main_row is not None:
            self.gpu_main_row.styles.layout = main_layout
        if self.gpu_left_column is not None:
            self.gpu_left_column.styles.width = layout.history_width
        if self.gpu_overview_widget is not None:
            self.gpu_overview_widget.styles.width = layout.overview_width
        if self.gpu_history_widget is not None:
            self.gpu_history_widget.styles.width = layout.history_width
        if self.gpu_detail_widget is not None:
            self.gpu_detail_widget.styles.width = layout.detail_width
        if self.gpu_process_widget is not None:
            self.gpu_process_widget.styles.width = layout.process_width
        if self.gpu_status_widget is not None:
            self.gpu_status_widget.styles.width = layout.status_width
