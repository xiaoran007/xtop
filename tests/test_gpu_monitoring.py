import importlib
import sys
import tempfile
import types
import unittest
from collections import deque
from pathlib import Path
from contextlib import ExitStack, contextmanager
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

        compact = tui.resolve_gpu_dashboard_layout(80, 24)
        too_small = tui.resolve_gpu_dashboard_layout(79, 23)
        mid_compact = tui.resolve_gpu_dashboard_layout(100, 30)
        normal = tui.resolve_gpu_dashboard_layout(120, 36)
        wide = tui.resolve_gpu_dashboard_layout(160, 48)
        same_height = tui.resolve_gpu_dashboard_layout(140, 36)

        self.assertEqual(compact.density, "compact")
        self.assertEqual(mid_compact.density, "compact")
        self.assertFalse(compact.too_small)
        self.assertTrue(too_small.too_small)
        self.assertEqual(normal.mode, "normal")
        self.assertEqual(wide.mode, "wide")
        self.assertGreater(wide.graph_width, compact.graph_width)
        self.assertGreater(wide.process_width, wide.resource_width)
        self.assertGreaterEqual(wide.detail_width, 50)
        self.assertEqual(wide.history_width + wide.detail_width, wide.overview_width)
        self.assertEqual(normal.history_width + normal.detail_width, normal.overview_width)
        self.assertEqual(compact.overview_card_count, 2)
        self.assertTrue(compact.overview_compact)
        self.assertFalse(compact.show_command_summary)
        self.assertTrue(wide.show_command_summary)
        self.assertLessEqual(same_height.process_rows, wide.process_rows)

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
                    pid=1235,
                    username="alice",
                    process_type="compute",
                    name="python",
                    command_summary="python train.py --config exp.yaml",
                    used_memory_mb=1024,
                ),
                SimpleNamespace(
                    pid=1234,
                    username="alice",
                    process_type="compute",
                    name="torchrun",
                    command_summary="torchrun fit.py",
                    used_memory_mb=20480,
                ),
            ],
        )
        layout = tui.resolve_gpu_dashboard_layout(180, 36)

        header_widget = tui.TopHeaderWidget()
        header_widget.selected_gpu = gpu_stats
        header_widget.backend_label = "NVML"
        header_rendered = str(header_widget.render_header("10:34:19"))

        self.assertIn("GPU: 0 > RTX 4090", header_rendered)
        self.assertIn("Backend: NVML", header_rendered)
        self.assertIn("[1-9] Switch", header_rendered)

        header_widget.dashboard_layout = tui.resolve_gpu_dashboard_layout(160, 48)
        header_widget.selected_gpu = SimpleNamespace(**{**gpu_stats.__dict__, "name": "Mock RTX 6000 48GB Max-Q Blackwell Edition"})
        wide_header = str(header_widget.render_header("13:29:50"))
        self.assertIn("48GB", wide_header)
        self.assertIn("[q] Quit", wide_header)
        self.assertNotIn("Graph...", wide_header)
        self.assertLessEqual(len(wide_header), 160)

        overview_widget = tui.GPUOverviewWidget()
        other_gpu = SimpleNamespace(**{**gpu_stats.__dict__, "gpu_id": 1, "utilization": 12})
        overview_widget.update_snapshot([gpu_stats, other_gpu], gpu_stats.gpu_id, layout, {0: deque([25, 50, 75], maxlen=120), 1: deque([5, 10, 12], maxlen=120)})
        overview_rendered = str(overview_widget.render_overview())

        self.assertIn("OVERVIEW", overview_rendered)
        self.assertIn("ACTIVE", overview_rendered)
        self.assertIn("RTX 4090", overview_rendered)
        self.assertIn("━", overview_rendered)

        history_widget = tui.GPUHistoryWidget()
        history_widget.update_snapshot(
            gpu_stats,
            4,
            deque([25, 50, 75], maxlen=120),
            deque([12000, 18000, 24576], maxlen=120),
            tui.GraphStyle.BRAILLE,
            layout,
            [gpu_stats],
            deque([120, 220, 320], maxlen=120),
            deque([50, 60, 72], maxlen=120),
        )
        history_rendered = str(history_widget.render_history())

        self.assertIn("HISTORY", history_rendered)
        self.assertIn("GPU UTILIZATION", history_rendered)
        self.assertIn("MEMORY USED", history_rendered)
        self.assertIn("POWER DRAW", history_rendered)
        self.assertIn("TEMPERATURE", history_rendered)
        self.assertNotIn("gpu-totals", history_rendered)
        self.assertIn("RTX 4090", history_rendered)

        long_name_gpu = SimpleNamespace(**{**gpu_stats.__dict__, "name": "Mock RTX 6000 48GB Max-Q Blackwell Edition"})
        history_widget.update_snapshot(
            long_name_gpu,
            4,
            deque([25, 50, 75], maxlen=120),
            deque([12000, 18000, 24576], maxlen=120),
            tui.GraphStyle.BRAILLE,
            layout,
            [long_name_gpu],
            deque([120, 220, 320], maxlen=120),
            deque([50, 60, 72], maxlen=120),
        )
        self.assertIn("48GB Max-Q", str(history_widget.render_history()))

        meter_widget = tui.GPUMeterWidget()
        meter_widget.update_snapshot([gpu_stats], gpu_stats.gpu_id, layout)
        meter_rendered = str(meter_widget.render_meters())

        self.assertIn("OVERVIEW", meter_rendered)
        self.assertIn("87%", meter_rendered)

        resource_widget = tui.SelectedGPUDetailPanel()
        resource_widget.update_snapshot(
            gpu_stats,
            layout,
            deque([0, 512, 1024, 2048], maxlen=120),
            deque([0, 256, 512, 1024], maxlen=120),
        )
        resource_rendered = str(resource_widget.render_detail())

        self.assertIn("SELECTED GPU", resource_rendered)
        self.assertIn("Memory", resource_rendered)
        self.assertIn("PCIe RX", resource_rendered)
        self.assertIn("█", resource_rendered)
        self.assertEqual(len({len(line) for line in resource_rendered.splitlines()}), 1)

        missing_detail_gpu = SimpleNamespace(gpu_id=2, name="Minimal GPU", processes=[])
        resource_widget.update_snapshot(missing_detail_gpu, layout)
        self.assertIn("n/a", str(resource_widget.render_detail()))

        process_widget = tui.GPUProcessWidget()
        process_widget.update_snapshot(gpu_stats, layout)
        process_rendered = str(process_widget.render_processes())

        self.assertIn("PROCESSES", process_rendered)
        self.assertLess(process_rendered.index("torchrun fit.py"), process_rendered.index("python train.py"))
        self.assertIn("n/a", process_rendered)
        self.assertIn("python train.py", process_rendered)

        status_widget = tui.StatusLineWidget()
        status_widget.update_snapshot(gpu_stats, ["mock data"], layout, "Mock")
        status_rendered = str(status_widget.render_status())

        self.assertIn("Backend: Mock", status_rendered)
        self.assertIn("Driver 550.54", status_rendered)
        self.assertIn("CUDA 12.4", status_rendered)
        self.assertIn("mock data", status_rendered)

    def test_compact_dashboard_renders_within_80_columns(self):
        with stub_textual_and_rich():
            tui = importlib.import_module("xtop.frontend.tui")

        layout = tui.resolve_gpu_dashboard_layout(80, 24)
        gpus = [
            SimpleNamespace(
                gpu_id=index,
                name=f"Mock RTX {6000 + index * 100}",
                utilization=10 + index * 20,
                memory_used=8192 + index * 1024,
                memory_total=49152,
                power_usage=80 + index * 20,
                power_limit=450,
                temperature=45 + index,
                fan_speed=30 + index,
                fan_speed_rpm=1200 + index * 20,
                driver_version="555.99",
                cuda_version="12.5",
                processes=[],
            )
            for index in range(4)
        ]
        histories = {gpu.gpu_id: deque([gpu.utilization - 5, gpu.utilization], maxlen=120) for gpu in gpus}

        overview = tui.GPUOverviewWidget()
        overview.update_snapshot(gpus, 3, layout, histories)
        overview_rendered = str(overview.render_overview())
        self.assertIn("Mock RTX 6300", overview_rendered)
        self.assertLessEqual(overview_rendered.count("Mock RTX"), 2)
        self.assertTrue(all(len(line) <= 80 for line in overview_rendered.splitlines()))

        history = tui.GPUHistoryWidget()
        selected_gpu = gpus[3]
        history.update_snapshot(
            selected_gpu,
            4,
            histories[selected_gpu.gpu_id],
            deque([12000, 13000], maxlen=120),
            tui.GraphStyle.BRAILLE,
            layout,
            gpus,
            deque([100, 180], maxlen=120),
            deque([50, 58], maxlen=120),
        )
        history_rendered = str(history.render_history())
        self.assertIn("UTIL", history_rendered)
        self.assertIn("MEM", history_rendered)
        self.assertIn("PWR", history_rendered)
        self.assertIn("TEMP", history_rendered)
        self.assertTrue(all(len(line) <= 80 for line in history_rendered.splitlines()))

        detail = tui.SelectedGPUDetailPanel()
        detail.update_snapshot(selected_gpu, layout)
        detail_rendered = str(detail.render_detail())
        self.assertTrue(all(len(line) <= 80 for line in detail_rendered.splitlines()))

        process_panel = tui.GPUProcessPanel()
        selected_gpu.processes = [
            SimpleNamespace(pid=1, username="xiaoran", name="python", command_summary="python train.py", used_memory_mb=1024)
        ]
        process_panel.update_snapshot(selected_gpu, layout)
        process_rendered = str(process_panel.render_processes())
        self.assertTrue(all(len(line) <= 80 for line in process_rendered.splitlines()))

    def test_compact_app_pages_toggle_visible_body_widget(self):
        with stub_textual_and_rich():
            tui = importlib.import_module("xtop.frontend.tui")

        class DummyWidget:
            def __init__(self):
                self.styles = SimpleNamespace()

        app = tui.XtopTUI.__new__(tui.XtopTUI)
        app.compact_body_page = "processes"
        app.gpu_main_row = DummyWidget()
        app.gpu_overview_row = DummyWidget()
        app.gpu_status_row = DummyWidget()
        app.gpu_left_column = DummyWidget()
        app.gpu_overview_widget = DummyWidget()
        app.gpu_history_widget = DummyWidget()
        app.gpu_detail_widget = DummyWidget()
        app.gpu_process_widget = DummyWidget()
        app.gpu_status_widget = DummyWidget()

        app._apply_dashboard_layout(tui.resolve_gpu_dashboard_layout(80, 24))
        self.assertEqual(app.gpu_history_widget.styles.display, "none")
        self.assertEqual(app.gpu_process_widget.styles.display, "block")
        self.assertEqual(app.gpu_detail_widget.styles.display, "none")

        app.compact_body_page = "details"
        app._apply_dashboard_layout(tui.resolve_gpu_dashboard_layout(80, 24))
        self.assertEqual(app.gpu_left_column.styles.display, "none")
        self.assertEqual(app.gpu_detail_widget.styles.display, "block")

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

    def test_nvidia_optional_detail_helpers_read_nvml_fields(self):
        with stub_pynvml() as fake_nvml:
            nvidia = importlib.import_module("xtop.backend.gpu.nvidia")

        fake_nvml.nvmlDeviceGetCurrPcieLinkGeneration = lambda handle: 4
        fake_nvml.nvmlDeviceGetMaxPcieLinkGeneration = lambda handle: 5
        fake_nvml.nvmlDeviceGetCurrPcieLinkWidth = lambda handle: 16
        fake_nvml.nvmlDeviceGetMaxPcieLinkWidth = lambda handle: 16
        fake_nvml.NVML_MEMORY_ERROR_TYPE_CORRECTED = 0
        fake_nvml.NVML_MEMORY_ERROR_TYPE_UNCORRECTED = 1
        fake_nvml.NVML_AGGREGATE_ECC = 0
        fake_nvml.NVML_VOLATILE_ECC = 1
        fake_nvml.nvmlDeviceGetTotalEccErrors = lambda handle, error_type, counter_type: 2 if error_type == 0 else 3
        fake_nvml.nvmlClocksThrottleReasonNone = 0
        fake_nvml.nvmlClocksThrottleReasonGpuIdle = 1
        fake_nvml.nvmlClocksThrottleReasonSwPowerCap = 4
        fake_nvml.nvmlDeviceGetCurrentClocksThrottleReasons = lambda handle: 5

        gpu = nvidia.NvidiaGPU.__new__(nvidia.NvidiaGPU)

        self.assertEqual(gpu._read_pcie_generation("handle"), "Gen4/max5")
        self.assertEqual(gpu._read_pcie_link_width("handle"), "x16")
        self.assertEqual(gpu._read_ecc_errors("handle"), 5)
        self.assertEqual(gpu._read_performance_cap("handle"), "Idle, SW Power")

    def test_jetson_backend_updates_unified_gpu_stats_fields(self):
        jetson = importlib.import_module("xtop.backend.gpu.jetson")
        models = importlib.import_module("xtop.backend.gpu.models")

        backend = jetson.JetsonGPU.__new__(jetson.JetsonGPU)
        backend.start = True
        backend.power_limit = None
        backend.gpus = [models.GPUStats(0, "Jetson Orin", "540.4.0 / L4T 36.4.7", "12.6", "8.7", uuid="jetson-uuid")]

        with ExitStack() as stack:
            stack.enter_context(patch.object(backend, "_get_memory_info", return_value=(7621.0, 813.0, 6808.0)))
            stack.enter_context(patch.object(backend, "_get_fan_info", return_value=(29, 1513)))
            stack.enter_context(patch.object(backend, "_get_gpu_clock_mhz", return_value=306))
            stack.enter_context(patch.object(backend, "_get_gpu_utilization", return_value=12))
            stack.enter_context(patch.object(backend, "_get_power_usage", return_value=0.6))
            stack.enter_context(patch.object(backend, "_get_gpu_temperature", return_value=43))
            stack.enter_context(patch.object(backend, "_get_emc_clock_mhz", return_value=None))
            stack.enter_context(patch.object(backend, "_read_current_user_processes", return_value=[]))
            stack.enter_context(patch.object(backend, "_format_system_uptime", return_value="01:02:03"))
            stack.enter_context(patch.object(backend, "_get_ecc_errors", return_value=0))
            backend.update()

        gpu = backend.gpus[0]
        self.assertEqual(gpu.utilization, 12)
        self.assertEqual(gpu.graphics_clock_mhz, 306)
        self.assertEqual(gpu.sm_clock_mhz, 306)
        self.assertIsNone(gpu.pcie_rx_kbps)
        self.assertEqual(gpu.uptime, "01:02:03")
        self.assertEqual(gpu.ecc_errors, 0)
        self.assertEqual(gpu.current_user_process_count, 0)

    def test_jetson_sysfs_helpers_read_jp6_fields_without_misusing_frequency_as_load(self):
        jetson = importlib.import_module("xtop.backend.gpu.jetson")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            gpu_path = root / "gpu"
            devfreq_path = root / "devfreq"
            thermal_path = root / "thermal"
            hwmon_path = root / "hwmon"
            ina_path = hwmon_path / "hwmon1"
            pwm_path = hwmon_path / "hwmon0"
            tach_path = hwmon_path / "hwmon2"
            ecc_path = gpu_path / "gr0_fecs_ecc_corrected_err_count"
            for path in (gpu_path, devfreq_path, thermal_path / "thermal_zone1", ina_path, pwm_path, tach_path):
                path.mkdir(parents=True)

            (devfreq_path / "cur_freq").write_text("306000000")
            (thermal_path / "thermal_zone1" / "type").write_text("gpu-thermal")
            (thermal_path / "thermal_zone1" / "temp").write_text("43718")
            (ina_path / "name").write_text("ina3221")
            (ina_path / "in1_label").write_text("VDD_IN")
            (ina_path / "in1_input").write_text("4968")
            (ina_path / "curr1_input").write_text("952")
            (ina_path / "in2_label").write_text("VDD_CPU_GPU_CV")
            (ina_path / "in2_input").write_text("4968")
            (ina_path / "curr2_input").write_text("104")
            (pwm_path / "name").write_text("pwmfan")
            (pwm_path / "pwm1").write_text("76")
            (tach_path / "name").write_text("pwm_tach")
            (tach_path / "rpm").write_text("1513")
            ecc_path.write_text("2")

            backend = jetson.JetsonGPU.__new__(jetson.JetsonGPU)
            backend.GPU_LOAD_PATHS = (str(root / "missing-load"),)
            backend.GPU_DEVFREQ_PATHS = (str(devfreq_path),)
            backend.GPU_PLATFORM_PATHS = (str(gpu_path),)
            backend.THERMAL_ZONE_PATH = str(thermal_path)
            backend.HWMON_PATH = str(hwmon_path)

            self.assertIsNone(backend._get_gpu_utilization())
            self.assertEqual(backend._get_gpu_clock_mhz(), 306)
            self.assertEqual(backend._get_gpu_temperature(), 43)
            self.assertEqual(backend._get_power_usage(), 0.5)
            self.assertEqual(backend._get_fan_info(), (29, 1513))
            self.assertEqual(backend._get_ecc_errors(), 2)

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
            self.assertIsNotNone(gpu.uuid)
            self.assertEqual(gpu.pcie_gen, "Gen4")
            self.assertEqual(gpu.pcie_link_width, "x16")
            self.assertIsNotNone(gpu.uptime)
            self.assertEqual(gpu.ecc_errors, 0)
            self.assertEqual(gpu.performance_cap, "None")
            self.assertGreaterEqual(len(gpu.processes), 1)
            self.assertEqual(gpu.current_user_process_count, len(gpu.processes))
            self.assertTrue(all(process.username == backend.current_username for process in gpu.processes))


if __name__ == "__main__":
    unittest.main()
