from importlib import import_module


__all__ = ["NvidiaGPU", "JetsonGPU"]


def __getattr__(name):
    if name == "NvidiaGPU":
        module = import_module("xtop.backend.gpu.nvidia")
        return getattr(module, name)
    if name == "JetsonGPU":
        module = import_module("xtop.backend.gpu.jetson")
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
