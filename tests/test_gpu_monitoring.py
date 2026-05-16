import importlib
import sys
import types
import unittest
from collections import deque
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch


@contextmanager
def stub_textual_and_rich():
    saved_modules = {}

    def register(name, module):
        saved_modules[name] = sys.modules.get(name)
        sys.modules[name] = module

    rich_module = types.ModuleType("rich")
    rich_console = types.ModuleType("rich.console")
    rich_text = types.ModuleType("rich.text")

    class Text:
        def __init__(self, text="", style=None):
            self.text = text
            self.style = style

        @classmethod
        def from_markup(cls, text):
            return cls(text)

        @classmethod
        def assemble(cls, *parts):
            return cls("".join(getattr(part, "text", str(part)) for part in parts))

        def join(self, items):
            return Text(self.text.join(getattr(item, "text", str(item)) for item in items))

        def __str__(self):
            return self.text

    rich_console.RenderableType = object
    rich_text.Text = Text

    textual_module = types.ModuleType("textual")
    textual_app = types.ModuleType("textual.app")
    textual_color = types.ModuleType("textual.color")
    textual_containers = types.ModuleType("textual.containers")
    textual_widgets = types.ModuleType("textual.widgets")

    class App:
        def __init__(self, *args, **kwargs):
            pass

        def run(self):
            pass

    class Color:
        def __init__(self, hex_value):
            self.hex = hex_value

        @classmethod
        def parse(cls, value):
            return cls(value)

        def lighten(self, _amount):
            return self

    class VerticalScroll:
        def __init__(self, *args, **kwargs):
            pass

    class Horizontal:
        def __init__(self, *args, **kwargs):
            pass

        def mount(self, *args, **kwargs):
            pass

    class Vertical:
        def __init__(self, *args, **kwargs):
            pass

        def mount(self, *args, **kwargs):
            pass

    class Static:
        def __init__(self, *args, **kwargs):
            pass

        def update(self, *args, **kwargs):
            pass

        def set_interval(self, *args, **kwargs):
            return None

    class Header:
        def __init__(self, *args, **kwargs):
            pass

    class Footer:
        def __init__(self, *args, **kwargs):
            pass

    textual_app.App = App
    textual_app.ComposeResult = object
    textual_color.Color = Color
    textual_containers.Horizontal = Horizontal
    textual_containers.Vertical = Vertical
    textual_containers.VerticalScroll = VerticalScroll
    textual_widgets.Footer = Footer
    textual_widgets.Header = Header
    textual_widgets.Static = Static

    register("rich", rich_module)
    register("rich.console", rich_console)
    register("rich.text", rich_text)
    register("textual", textual_module)
    register("textual.app", textual_app)
    register("textual.color", textual_color)
    register("textual.containers", textual_containers)
    register("textual.widgets", textual_widgets)

    try:
        yield
    finally:
        for name, module in saved_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


@contextmanager
def stub_pynvml():
    saved_module = sys.modules.get("pynvml")
    fake_module = types.ModuleType("pynvml")

    class NVMLError(Exception):
        pass

    fake_module.NVMLError = NVMLError
    fake_module.nvmlSystemGetProcessName = lambda pid: f"proc-{pid}".encode()

    sys.modules["pynvml"] = fake_module
    try:
        yield fake_module
    finally:
        if saved_module is None:
            sys.modules.pop("pynvml", None)
        else:
            sys.modules["pynvml"] = saved_module


class GPUMonitoringTests(unittest.TestCase):
    def tearDown(self):
        for name in [
            "xtop.frontend.tui",
            "xtop.frontend.tui_app",
            "xtop.frontend.tui_backends",
            "xtop.frontend.tui_graphs",
            "xtop.frontend.tui_layout",
            "xtop.frontend.tui_widgets",
            "xtop.backend.gpu.nvidia",
            "xtop.backend.gpu.mock",
            "xtop.backend.gpu.models",
        ]:
            sys.modules.pop(name, None)

    def test_resolve_gpu_widget_layout_adapts_to_terminal_size(self):
        with stub_textual_and_rich():
            tui = importlib.import_module("xtop.frontend.tui")

        compact = tui.resolve_gpu_widget_layout(64, 20)
        wide = tui.resolve_gpu_widget_layout(128, 36)

        self.assertTrue(compact.compact_process_rows)
        self.assertEqual(compact.process_limit, 2)
        self.assertTrue(wide.show_extended_metrics)
        self.assertTrue(wide.show_command_summary)
        self.assertGreater(wide.process_limit, compact.process_limit)

    def test_dashboard_layout_expands_graph_width_and_fixes_process_budget(self):
        with stub_textual_and_rich():
            tui = importlib.import_module("xtop.frontend.tui")

        narrow = tui.resolve_gpu_dashboard_layout(88, 32)
        normal = tui.resolve_gpu_dashboard_layout(128, 32)
        wide = tui.resolve_gpu_dashboard_layout(220, 32)
        same_height = tui.resolve_gpu_dashboard_layout(140, 32)

        self.assertEqual(narrow.mode, "narrow")
        self.assertEqual(normal.mode, "normal")
        self.assertEqual(wide.mode, "wide")
        self.assertGreater(wide.graph_width, narrow.graph_width)
        self.assertGreater(wide.process_width, wide.resource_width)
        self.assertFalse(narrow.show_command_summary)
        self.assertTrue(wide.show_command_summary)
        self.assertEqual(same_height.process_rows, wide.process_rows)

    def test_btop_style_widgets_render_selected_gpu_blocks(self):
        with stub_textual_and_rich():
            tui = importlib.import_module("xtop.frontend.tui")

        gpu_stats = SimpleNamespace(
            gpu_id=0,
            name="RTX 4090",
            driver_version="550.54",
            cuda_version="12.4",
            cuda_cc="8.9",
            utilization=87,
            memory_used=24576,
            memory_total=49152,
            memory_free=24576,
            power_usage=320.0,
            power_limit=450.0,
            temperature=72,
            fan_speed=48,
            fan_speed_rpm=1800,
            graphics_clock_mhz=2520,
            sm_clock_mhz=2520,
            memory_clock_mhz=10501,
            p_state="P0",
            pcie_rx_kbps=2048,
            pcie_tx_kbps=1024,
            processes=[
                SimpleNamespace(
                    pid=1234,
                    username="alice",
                    process_type="compute",
                    name="python",
                    command_summary="python train.py --config exp.yaml",
                    used_memory_mb=20480,
                )
            ],
        )
        layout = tui.resolve_gpu_dashboard_layout(180, 36)

        history_widget = tui.GPUHistoryWidget()
        history_widget.update_snapshot(gpu_stats, 4, deque([25, 50, 75], maxlen=120), deque([20, 30, 40], maxlen=120), tui.GraphStyle.BRAILLE, layout, [gpu_stats])
        history_rendered = str(history_widget.render_history())

        self.assertIn("gpu 1/4", history_rendered)
        self.assertIn("meters", history_rendered)
        self.assertIn("RTX 4090", history_rendered)

        meter_widget = tui.GPUMeterWidget()
        meter_widget.update_snapshot([gpu_stats], gpu_stats.gpu_id, layout)
        meter_rendered = str(meter_widget.render_meters())

        self.assertIn("meters", meter_rendered)
        self.assertIn("87%", meter_rendered)

        resource_widget = tui.GPUResourceWidget()
        resource_widget.update_snapshot(gpu_stats, layout)
        resource_rendered = str(resource_widget.render_resources())

        self.assertIn("mem/power", resource_rendered)
        self.assertIn("Total", resource_rendered)

        process_widget = tui.GPUProcessWidget()
        process_widget.update_snapshot(gpu_stats, layout)
        process_rendered = str(process_widget.render_processes())

        self.assertIn("proc", process_rendered)
        self.assertIn("python train.py", process_rendered)

        status_widget = tui.GPUStatusWidget()
        status_widget.update_snapshot(gpu_stats, ["mock data"], layout)
        status_rendered = str(status_widget.render_status())

        self.assertIn("device/status", status_rendered)
        self.assertIn("Driver 550.54", status_rendered)
        self.assertIn("mock data", status_rendered)

    def test_process_panel_height_is_stable_when_process_count_changes(self):
        with stub_textual_and_rich():
            tui = importlib.import_module("xtop.frontend.tui")

        layout = tui.resolve_gpu_dashboard_layout(180, 36)
        one_process = [
            SimpleNamespace(pid=100, process_type="compute", name="python", command_summary="python train.py", used_memory_mb=1024)
        ]
        three_processes = one_process + [
            SimpleNamespace(pid=101, process_type="compute", name="torchrun", command_summary="torchrun job.py", used_memory_mb=2048),
            SimpleNamespace(pid=102, process_type="compute", name="python", command_summary="python serve.py", used_memory_mb=512),
        ]

        one_rendered = "\n".join(str(line) for line in tui.build_process_panel_lines(one_process, layout))
        three_rendered = "\n".join(str(line) for line in tui.build_process_panel_lines(three_processes, layout))

        self.assertEqual(one_rendered.count("\n"), three_rendered.count("\n"))
        self.assertIn("python train.py", one_rendered)
        self.assertIn("torchrun job.py", three_rendered)

    def test_gpu_widget_keeps_graph_when_widget_height_is_transiently_small(self):
        with stub_textual_and_rich():
            tui = importlib.import_module("xtop.frontend.tui")

        gpu_stats = SimpleNamespace(
            gpu_id=0,
            name="RTX 4090",
            driver_version="550.54",
            cuda_version="12.4",
            cuda_cc="8.9",
            utilization=50,
            memory_used=1024,
            memory_total=24576,
            memory_free=23552,
            power_usage=200.0,
            power_limit=450.0,
            temperature=65,
            fan_speed=35,
            fan_speed_rpm=1200,
            graphics_clock_mhz=2100,
            sm_clock_mhz=2100,
            memory_clock_mhz=10000,
            p_state="P2",
            pcie_rx_kbps=512,
            pcie_tx_kbps=512,
            processes=[],
        )

        widget = tui.GPUStatsWidget(gpu_stats)
        widget.size = SimpleNamespace(width=120, height=1)
        widget.app = SimpleNamespace(size=SimpleNamespace(width=120, height=36))
        rendered = str(widget.render_stats())

        self.assertIn("⣴", rendered)

    def test_nvidia_process_stats_are_filtered_by_current_user(self):
        with stub_pynvml():
            nvidia = importlib.import_module("xtop.backend.gpu.nvidia")

        gpu = nvidia.NvidiaGPU.__new__(nvidia.NvidiaGPU)
        gpu.current_username = "alice"

        class FakeProcess:
            def __init__(self, pid, username):
                self._pid = pid
                self._username = username

            def username(self):
                return self._username

            def name(self):
                return "python"

            def cmdline(self):
                return ["python", "train.py", "--epochs", "1"]

        with patch.object(nvidia.psutil, "Process", side_effect=[FakeProcess(100, "alice"), FakeProcess(101, "bob")]):
            current_user = gpu._build_process_stats(100, "compute", 512.0)
            other_user = gpu._build_process_stats(101, "compute", 256.0)

        self.assertIsNotNone(current_user)
        self.assertEqual(current_user.name, "python")
        self.assertIn("train.py", current_user.command_summary)
        self.assertIsNone(other_user)

    def test_mock_gpu_backend_updates_multi_gpu_current_user_processes(self):
        mock = importlib.import_module("xtop.backend.gpu.mock")

        backend = mock.MockNvidiaGPU(gpu_number=2)
        backend.init()
        backend.update()

        self.assertEqual(backend.gpu_number, 2)
        self.assertEqual(len(backend.gpus), 2)
        for gpu in backend.gpus:
            self.assertIsNotNone(gpu.utilization)
            self.assertGreater(gpu.memory_total, 0)
            self.assertGreaterEqual(len(gpu.processes), 1)
            self.assertEqual(gpu.current_user_process_count, len(gpu.processes))
            self.assertTrue(all(process.username == backend.current_username for process in gpu.processes))


if __name__ == "__main__":
    unittest.main()
