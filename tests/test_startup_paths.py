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


class StartupPathTests(unittest.TestCase):
    def tearDown(self):
        for name in [
            "xtop.frontend.tui",
            "xtop.frontend.tui_app",
            "xtop.frontend.tui_backends",
            "xtop.frontend.tui_graphs",
            "xtop.frontend.tui_layout",
            "xtop.frontend.tui_widgets",
            "xtop.frontend",
            "xtop.backend.gpu",
            "xtop.backend.gpu.mock",
            "xtop.backend.gpu.models",
        ]:
            sys.modules.pop(name, None)

    def test_frontend_and_gpu_packages_import_without_optional_backends(self):
        frontend = importlib.import_module("xtop.frontend")
        backend_gpu = importlib.import_module("xtop.backend.gpu")

        self.assertEqual(frontend.__all__, ["GPU_UI", "GPU_UI_Jetson", "NPU_UI"])
        self.assertEqual(backend_gpu.__all__, ["NvidiaGPU", "JetsonGPU", "MockNvidiaGPU"])
        self.assertNotIn("xtop.backend.gpu.nvidia", sys.modules)
        self.assertNotIn("xtop.backend.npu.intel", sys.modules)

    def test_tui_module_import_does_not_pull_optional_backends(self):
        with stub_textual_and_rich():
            tui = importlib.import_module("xtop.frontend.tui")

        self.assertTrue(hasattr(tui, "XtopTUI"))
        self.assertNotIn("xtop.backend.gpu.nvidia", sys.modules)
        self.assertNotIn("xtop.backend.npu.intel", sys.modules)

    def test_resolve_tui_targets_uses_platform_aware_defaults(self):
        main_module = importlib.import_module("xtop.__main__")

        self.assertEqual(
            main_module.resolve_tui_targets("macos", SimpleNamespace(gpu=False, npu=False)),
            (False, True, False),
        )
        self.assertEqual(
            main_module.resolve_tui_targets("linux", SimpleNamespace(gpu=False, npu=False)),
            (True, False, False),
        )
        self.assertEqual(
            main_module.resolve_tui_targets("macos", SimpleNamespace(gpu=True, npu=False)),
            (True, False, False),
        )
        self.assertEqual(
            main_module.resolve_tui_targets("macos", SimpleNamespace(gpu=False, npu=True)),
            (False, False, True),
        )
        self.assertEqual(
            main_module.resolve_tui_targets("macos", SimpleNamespace(gpu=False, npu=False, mock_gpu=True)),
            (True, False, False),
        )

    def test_parser_keeps_textual_default_and_legacy_flags(self):
        main_module = importlib.import_module("xtop.__main__")
        parser = main_module.build_arg_parser()

        defaults = parser.parse_args([])
        legacy_gpu = parser.parse_args(["--legacy", "-g", "-l"])
        mock_gpu = parser.parse_args(["--mock-gpu"])
        textual_alias = parser.parse_args(["--tui"])

        self.assertFalse(defaults.legacy)
        self.assertFalse(defaults.tui)
        self.assertTrue(legacy_gpu.legacy)
        self.assertTrue(legacy_gpu.gpu)
        self.assertTrue(legacy_gpu.log)
        self.assertTrue(mock_gpu.mock_gpu)
        self.assertTrue(textual_alias.tui)

    def test_load_gpu_backend_prefers_jetson_without_importing_nvidia(self):
        with stub_textual_and_rich():
            tui = importlib.import_module("xtop.frontend.tui")

        class FakeJetsonGPU:
            @staticmethod
            def is_jetson_device():
                return True

        fake_jetson_module = types.SimpleNamespace(JetsonGPU=FakeJetsonGPU)

        def fake_import(name):
            if name == "xtop.backend.gpu.jetson":
                return fake_jetson_module
            if name == "xtop.backend.gpu.nvidia":
                raise AssertionError("Nvidia backend should not be imported for Jetson devices")
            raise ImportError(name)

        tui_backends = importlib.import_module("xtop.frontend.tui_backends")

        with patch.object(tui_backends.importlib, "import_module", side_effect=fake_import):
            backend, error = tui.load_gpu_backend()

        self.assertIsInstance(backend, FakeJetsonGPU)
        self.assertIsNone(error)

    def test_load_gpu_backend_can_use_mock_without_nvidia_backend(self):
        with stub_textual_and_rich():
            tui = importlib.import_module("xtop.frontend.tui")

        backend, error = tui.load_gpu_backend(use_mock=True)

        self.assertEqual(type(backend).__name__, "MockNvidiaGPU")
        self.assertIsNone(error)
        self.assertNotIn("xtop.backend.gpu.nvidia", sys.modules)

    def test_status_messages_cover_unimplemented_and_unavailable_states(self):
        with stub_textual_and_rich():
            tui = importlib.import_module("xtop.frontend.tui")

        messages = tui.build_status_messages(
            "macos",
            enable_gpu=True,
            enable_cpu=True,
            enable_npu=True,
            gpu_error="No module named 'pynvml'",
            npu_error="No module named 'pypci'",
        )

        self.assertIn("Apple CPU monitoring is not implemented yet.", messages)
        self.assertIn("GPU monitoring is unavailable on this system: No module named 'pynvml'", messages)
        self.assertIn("NPU monitoring is unavailable on this system: No module named 'pypci'", messages)


if __name__ == "__main__":
    unittest.main()
