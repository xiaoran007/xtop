import importlib
from typing import Optional


def resolve_cpu_status_message(os_name: str) -> str:
    """Describe the current state of CPU support."""
    if os_name == "macos":
        return "Apple CPU monitoring is not implemented yet."
    return "CPU monitoring is not implemented yet."


def resolve_gpu_unavailable_message(reason: Optional[str] = None) -> str:
    """Describe why GPU monitoring is unavailable."""
    if reason:
        return f"GPU monitoring is unavailable on this system: {reason}"
    return "GPU monitoring is unavailable on this system."


def resolve_npu_unavailable_message(reason: Optional[str] = None) -> str:
    """Describe why NPU monitoring is unavailable."""
    if reason:
        return f"NPU monitoring is unavailable on this system: {reason}"
    return "NPU monitoring is unavailable on this system."


def build_status_messages(
    os_name: str,
    *,
    enable_gpu: bool,
    enable_cpu: bool,
    enable_npu: bool,
    gpu_error: Optional[str] = None,
    npu_error: Optional[str] = None,
) -> list[str]:
    """Collect user-facing status messages for requested monitors."""
    messages = []
    if enable_cpu:
        messages.append(resolve_cpu_status_message(os_name))
    if enable_gpu and gpu_error:
        messages.append(resolve_gpu_unavailable_message(gpu_error))
    if enable_npu and npu_error:
        messages.append(resolve_npu_unavailable_message(npu_error))
    return messages


def load_gpu_backend(use_mock: bool = False):
    """Load the GPU backend lazily, preferring Jetson when applicable."""
    if use_mock:
        mock_module = importlib.import_module("xtop.backend.gpu.mock")
        return mock_module.MockNvidiaGPU(), None

    try:
        jetson_module = importlib.import_module("xtop.backend.gpu.jetson")
        if jetson_module.JetsonGPU.is_jetson_device():
            return jetson_module.JetsonGPU(), None
    except Exception:
        pass

    try:
        nvidia_module = importlib.import_module("xtop.backend.gpu.nvidia")
        return nvidia_module.NvidiaGPU(), None
    except ImportError as exc:
        return None, str(exc)
    except Exception:
        return None, "backend could not be loaded"


def load_npu_backend():
    """Load the Intel NPU backend lazily."""
    try:
        npu_module = importlib.import_module("xtop.backend.npu.intel")
        return npu_module.IntelNPU(), None
    except ImportError as exc:
        return None, str(exc)
    except Exception:
        return None, "backend could not be loaded"
