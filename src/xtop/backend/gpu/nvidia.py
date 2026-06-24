import time
from typing import Callable, Optional

import pynvml
import psutil

from .models import GPUProcessStats, GPUStats


def _decode_text(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _normalize_username(username: Optional[str]) -> str:
    if not username:
        return ""
    return username.split("\\")[-1].split("/")[-1].lower()


def _safe_join_command(cmdline: list[str]) -> Optional[str]:
    if not cmdline:
        return None
    return " ".join(part for part in cmdline if part)


def _read_nvml_call(default, callback: Callable):
    try:
        return callback()
    except pynvml.NVMLError:
        return default


class NvidiaGPU:
    def __init__(self):
        self.gpu_number: int = 0
        self.gpus: list[GPUStats] = []
        self.start: bool = False
        self.current_username = _normalize_username(psutil.Process().username())

    def init(self):
        pynvml.nvmlInit()
        self.gpu_number = pynvml.nvmlDeviceGetCount()
        for i in range(self.gpu_number):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            name = _decode_text(pynvml.nvmlDeviceGetName(handle))
            driver_version = _decode_text(pynvml.nvmlSystemGetDriverVersion())
            cuda_version = self.__convertCudaDriverVersion(pynvml.nvmlSystemGetCudaDriverVersion())
            cuda_cc = self.__convertCudaCC(pynvml.nvmlDeviceGetCudaComputeCapability(handle))
            uuid = _read_nvml_call(None, lambda: _decode_text(pynvml.nvmlDeviceGetUUID(handle)))
            gpu = GPUStats(i, name, driver_version, cuda_version, cuda_cc, uuid=uuid)
            self.gpus.append(gpu)
        self.start = True

    def shutdown(self):
        pynvml.nvmlShutdown()
        self.start = False

    def update(self):
        for gpu in self.gpus:
            handle = pynvml.nvmlDeviceGetHandleByIndex(gpu.gpu_id)
            utilization_rates = _read_nvml_call(None, lambda: pynvml.nvmlDeviceGetUtilizationRates(handle))
            utilization = getattr(utilization_rates, "gpu", None)
            mem_info = _read_nvml_call(None, lambda: pynvml.nvmlDeviceGetMemoryInfo(handle))
            temperature = _read_nvml_call(None, lambda: pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU))

            fan_speed = _read_nvml_call(None, lambda: pynvml.nvmlDeviceGetFanSpeed(handle))
            fan_speed_rpm = _read_nvml_call(None, lambda: pynvml.nvmlDeviceGetFanSpeedRPM(handle))
            power_usage = _read_nvml_call(None, lambda: round(pynvml.nvmlDeviceGetPowerUsage(handle) / 1000, 1))
            power_limit = _read_nvml_call(None, lambda: round(pynvml.nvmlDeviceGetPowerManagementLimit(handle) / 1000, 1))
            p_state = _read_nvml_call(None, lambda: f"P{pynvml.nvmlDeviceGetPerformanceState(handle)}")
            graphics_clock_mhz = self._read_clock(handle, "NVML_CLOCK_GRAPHICS")
            sm_clock_mhz = self._read_clock(handle, "NVML_CLOCK_SM")
            memory_clock_mhz = self._read_clock(handle, "NVML_CLOCK_MEM")
            pcie_tx_kbps = self._read_pcie_throughput(handle, "NVML_PCIE_UTIL_TX_BYTES")
            pcie_rx_kbps = self._read_pcie_throughput(handle, "NVML_PCIE_UTIL_RX_BYTES")
            pcie_gen = self._read_pcie_generation(handle)
            pcie_link_width = self._read_pcie_link_width(handle)
            uptime = self._format_system_uptime()
            ecc_errors = self._read_ecc_errors(handle)
            performance_cap = self._read_performance_cap(handle)
            processes = self._read_current_user_processes(handle)

            mem_used = mem_info.used / (1024 ** 2) if mem_info is not None else None
            mem_total = mem_info.total / (1024 ** 2) if mem_info is not None else None
            mem_free = mem_info.free / (1024 ** 2) if mem_info is not None else None
            gpu.update(
                utilization=utilization,
                memory_used=mem_used,
                memory_total=mem_total,
                memory_free=mem_free,
                power_usage=power_usage,
                temperature=temperature,
                fan_speed=fan_speed,
                fan_speed_rpm=fan_speed_rpm,
                power_limit=power_limit,
                p_state=p_state,
                graphics_clock_mhz=graphics_clock_mhz,
                sm_clock_mhz=sm_clock_mhz,
                memory_clock_mhz=memory_clock_mhz,
                pcie_tx_kbps=pcie_tx_kbps,
                pcie_rx_kbps=pcie_rx_kbps,
                processes=processes,
                pcie_gen=pcie_gen,
                pcie_link_width=pcie_link_width,
                uptime=uptime,
                ecc_errors=ecc_errors,
                performance_cap=performance_cap,
            )

    def _read_clock(self, handle, constant_name: str) -> Optional[int]:
        clock_type = getattr(pynvml, constant_name, None)
        if clock_type is None:
            return None
        return _read_nvml_call(None, lambda: pynvml.nvmlDeviceGetClockInfo(handle, clock_type))

    def _read_pcie_throughput(self, handle, constant_name: str) -> Optional[int]:
        counter = getattr(pynvml, constant_name, None)
        if counter is None:
            return None
        return _read_nvml_call(None, lambda: pynvml.nvmlDeviceGetPcieThroughput(handle, counter))

    def _read_pcie_generation(self, handle) -> Optional[str]:
        current_getter = getattr(pynvml, "nvmlDeviceGetCurrPcieLinkGeneration", None)
        max_getter = getattr(pynvml, "nvmlDeviceGetMaxPcieLinkGeneration", None)
        if current_getter is None:
            return None
        current = _read_nvml_call(None, lambda: current_getter(handle))
        if current is None:
            return None
        maximum = _read_nvml_call(None, lambda: max_getter(handle)) if max_getter is not None else None
        if maximum and maximum != current:
            return f"Gen{current}/max{maximum}"
        return f"Gen{current}"

    def _read_pcie_link_width(self, handle) -> Optional[str]:
        current_getter = getattr(pynvml, "nvmlDeviceGetCurrPcieLinkWidth", None)
        max_getter = getattr(pynvml, "nvmlDeviceGetMaxPcieLinkWidth", None)
        if current_getter is None:
            return None
        current = _read_nvml_call(None, lambda: current_getter(handle))
        if current is None:
            return None
        maximum = _read_nvml_call(None, lambda: max_getter(handle)) if max_getter is not None else None
        if maximum and maximum != current:
            return f"x{current}/max{maximum}"
        return f"x{current}"

    def _read_ecc_errors(self, handle) -> Optional[int]:
        getter = getattr(pynvml, "nvmlDeviceGetTotalEccErrors", None)
        corrected = getattr(pynvml, "NVML_MEMORY_ERROR_TYPE_CORRECTED", None)
        uncorrected = getattr(pynvml, "NVML_MEMORY_ERROR_TYPE_UNCORRECTED", None)
        aggregate = getattr(pynvml, "NVML_AGGREGATE_ECC", None)
        volatile = getattr(pynvml, "NVML_VOLATILE_ECC", None)
        if getter is None or corrected is None or uncorrected is None:
            return None

        for counter_type in (aggregate, volatile):
            if counter_type is None:
                continue
            corrected_count = _read_nvml_call(None, lambda counter_type=counter_type: getter(handle, corrected, counter_type))
            uncorrected_count = _read_nvml_call(None, lambda counter_type=counter_type: getter(handle, uncorrected, counter_type))
            if corrected_count is not None or uncorrected_count is not None:
                return (corrected_count or 0) + (uncorrected_count or 0)
        return None

    def _read_performance_cap(self, handle) -> Optional[str]:
        getter = getattr(pynvml, "nvmlDeviceGetCurrentClocksThrottleReasons", None)
        if getter is None:
            return None
        reasons = _read_nvml_call(None, lambda: getter(handle))
        if reasons is None:
            return None

        reason_map = (
            ("GpuIdle", "Idle"),
            ("ApplicationsClocksSetting", "App Clocks"),
            ("SwPowerCap", "SW Power"),
            ("HwSlowdown", "HW Slowdown"),
            ("SyncBoost", "Sync Boost"),
            ("SwThermalSlowdown", "SW Thermal"),
            ("HwThermalSlowdown", "HW Thermal"),
            ("HwPowerBrakeSlowdown", "HW Power Brake"),
            ("DisplayClockSetting", "Display Clock"),
        )
        labels = []
        for constant_suffix, label in reason_map:
            bit = getattr(pynvml, f"nvmlClocksThrottleReason{constant_suffix}", None)
            if bit is not None and reasons & bit:
                labels.append(label)
        if labels:
            return ", ".join(labels)
        none_bit = getattr(pynvml, "nvmlClocksThrottleReasonNone", None)
        if none_bit is not None and reasons == none_bit:
            return "None"
        return "None" if reasons == 0 else f"0x{reasons:x}"

    @staticmethod
    def _format_system_uptime() -> str:
        seconds = max(0, int(time.time() - psutil.boot_time()))
        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        if days:
            return f"{days}d {hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def _read_current_user_processes(self, handle) -> list[GPUProcessStats]:
        processes = []
        seen = set()

        for process_type, getter_names in (
            ("compute", ("nvmlDeviceGetComputeRunningProcesses_v3", "nvmlDeviceGetComputeRunningProcesses_v2", "nvmlDeviceGetComputeRunningProcesses")),
            ("graphics", ("nvmlDeviceGetGraphicsRunningProcesses_v3", "nvmlDeviceGetGraphicsRunningProcesses_v2", "nvmlDeviceGetGraphicsRunningProcesses")),
            ("mps", ("nvmlDeviceGetMPSComputeRunningProcesses_v3", "nvmlDeviceGetMPSComputeRunningProcesses_v2", "nvmlDeviceGetMPSComputeRunningProcesses")),
        ):
            getter = self._get_first_available(getter_names)
            if getter is None:
                continue

            for raw_process in _read_nvml_call([], lambda getter=getter: getter(handle)):
                pid = getattr(raw_process, "pid", None)
                if pid is None:
                    continue
                dedupe_key = (process_type, pid)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)

                process = self._build_process_stats(pid, process_type, self._convert_used_gpu_memory(getattr(raw_process, "usedGpuMemory", None)))
                if process is not None:
                    processes.append(process)

        return sorted(processes, key=lambda process: (process.used_memory_mb or 0, -process.pid), reverse=True)

    def _build_process_stats(self, pid: int, process_type: str, used_memory_mb: Optional[float]) -> Optional[GPUProcessStats]:
        try:
            process = psutil.Process(pid)
            username = process.username()
            if _normalize_username(username) != self.current_username:
                return None
            name = process.name()
            command_summary = _safe_join_command(process.cmdline())
        except (psutil.Error, OSError):
            username = None
            name = None
            command_summary = None

        if username is None:
            return None

        if not name:
            name = _read_nvml_call(None, lambda: _decode_text(pynvml.nvmlSystemGetProcessName(pid)))

        return GPUProcessStats(
            pid=pid,
            process_type=process_type,
            username=username,
            name=name,
            command_summary=command_summary,
            used_memory_mb=used_memory_mb,
        )

    @staticmethod
    def _get_first_available(names: tuple[str, ...]):
        for name in names:
            getter = getattr(pynvml, name, None)
            if getter is not None:
                return getter
        return None

    @staticmethod
    def _convert_used_gpu_memory(value) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, int) and value >= (1 << 63):
            return None
        return value / (1024 ** 2)

    @staticmethod
    def __convertCudaDriverVersion(version: int) -> str:
        major = version // 1000
        minor = (version % 1000) // 10
        return f"{major}.{minor}"

    @staticmethod
    def __convertCudaCC(cuda_cc: tuple) -> str:
        return f"{cuda_cc[0]}.{cuda_cc[1]}"
