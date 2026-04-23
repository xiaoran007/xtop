import importlib
import sys
import types
import unittest
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
            "xtop.backend.gpu.nvidia",
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

    def test_gpu_widget_renders_process_section_and_extended_metrics(self):
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

        widget = tui.GPUStatsWidget(gpu_stats)
        widget.size = SimpleNamespace(width=128, height=36)
        rendered = str(widget.render_stats())

        self.assertIn("Processes (current user): 1", rendered)
        self.assertIn("Clocks GFX/SM/MEM", rendered)
        self.assertIn("PCIe RX/TX", rendered)
        self.assertIn("python train.py", rendered)

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


if __name__ == "__main__":
    unittest.main()
