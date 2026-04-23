from importlib import import_module


__all__ = ["GPU_UI", "GPU_UI_Jetson", "NPU_UI"]


def __getattr__(name):
    if name in {"GPU_UI", "GPU_UI_Jetson"}:
        module = import_module("xtop.frontend.gpu")
        return getattr(module, name)
    if name == "NPU_UI":
        module = import_module("xtop.frontend.npu")
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
