import glob
import json
import os
import re
import subprocess
import time
from typing import Optional

import psutil

from .models import GPUProcessStats, GPUStats


class JetsonGPU:
    """Jetson GPU monitoring backend using Jetson Linux sysfs interfaces."""

    GPU_PLATFORM_PATHS = (
        "/sys/devices/platform/17000000.gpu",
        "/sys/devices/platform/gpu.0",
        "/sys/devices/gpu.0",
    )
    GPU_LOAD_PATHS = (
        "/sys/devices/platform/17000000.gpu/load",
        "/sys/devices/platform/gpu.0/load",
        "/sys/devices/gpu.0/load",
    )
    GPU_DEVFREQ_PATHS = (
        "/sys/devices/platform/17000000.gpu/devfreq/17000000.gpu",
        "/sys/devices/platform/17000000.gpu/devfreq_dev",
        "/sys/class/devfreq/17000000.gpu",
    )
    THERMAL_ZONE_PATH = "/sys/class/thermal"
    HWMON_PATH = "/sys/class/hwmon"
    GPU_PROCESS_DEVICES = {
        "/dev/nvidia0",
        "/dev/nvhost-gpu",
        "/dev/nvhost-as-gpu",
        "/dev/nvhost-ctrl-gpu",
        "/dev/nvhost-tsg-gpu",
        "/dev/nvgpu/igpu0/as",
        "/dev/nvgpu/igpu0/channel",
        "/dev/nvgpu/igpu0/ctrl",
        "/dev/nvgpu/igpu0/tsg",
    }

    def __init__(self):
        self.gpu_number: int = 1
        self.gpus: list[GPUStats] = []
        self.start: bool = False
        self.current_uid = os.getuid()
        self.current_username = self._normalize_username(psutil.Process().username())
        self.power_limit = None

    def init(self):
        """Initialize Jetson GPU monitoring."""
        device_name = self._get_device_name()
        l4t_version = self._get_l4t_version()
        nvidia_smi_info = self._get_nvidia_smi_identity()
        driver_version = self._format_driver_version(l4t_version, nvidia_smi_info.get("driver_version"))
        cuda_version = self._get_cuda_version()
        cuda_cc = self._get_cuda_cc(device_name)
        uuid = nvidia_smi_info.get("uuid")
        self.power_limit = self._get_power_limit()

        self.gpus.append(GPUStats(0, device_name, driver_version, cuda_version, cuda_cc, uuid=uuid))
        self.start = True

    def shutdown(self):
        """Shutdown Jetson GPU monitoring."""
        self.start = False

    def update(self):
        """Update GPU statistics."""
        if not self.start:
            return

        gpu = self.gpus[0]
        mem_total, mem_used, mem_free = self._get_memory_info()
        fan_speed, fan_speed_rpm = self._get_fan_info()
        graphics_clock_mhz = self._get_gpu_clock_mhz()

        gpu.update(
            utilization=self._get_gpu_utilization(),
            memory_used=mem_used,
            memory_total=mem_total,
            memory_free=mem_free,
            power_usage=self._get_power_usage(),
            temperature=self._get_gpu_temperature(),
            fan_speed=fan_speed,
            fan_speed_rpm=fan_speed_rpm,
            power_limit=self.power_limit,
            p_state=None,
            graphics_clock_mhz=graphics_clock_mhz,
            sm_clock_mhz=graphics_clock_mhz,
            memory_clock_mhz=self._get_emc_clock_mhz(),
            pcie_tx_kbps=None,
            pcie_rx_kbps=None,
            processes=self._read_current_user_processes(),
            pcie_gen=None,
            pcie_link_width=None,
            uptime=self._format_system_uptime(),
            ecc_errors=self._get_ecc_errors(),
            performance_cap=None,
        )

    def _read_sys_file(self, path: str, default=None):
        try:
            with open(path, "r") as file:
                return file.read().strip()
        except OSError:
            return default

    def _run_command(self, command: list[str], timeout: float = 1.0) -> Optional[str]:
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        return result.stdout.strip()

    @staticmethod
    def _normalize_username(username: Optional[str]) -> str:
        if not username:
            return ""
        return username.split("\\")[-1].split("/")[-1].lower()

    def _get_device_name(self) -> str:
        model = self._read_sys_file("/proc/device-tree/model", "")
        if model:
            return model.rstrip("\x00")

        compatible = self._read_sys_file("/proc/device-tree/compatible", "")
        if "jetson" in compatible.lower():
            for part in compatible.split("\x00"):
                if "jetson" in part.lower():
                    return part

        return "NVIDIA Jetson"

    def _get_l4t_version(self) -> str:
        content = self._read_sys_file("/etc/nv_tegra_release", "")
        if content:
            match = re.search(r"R(\d+).*?REVISION:\s*([\d.]+)", content)
            if match:
                return f"L4T {match.group(1)}.{match.group(2)}"
        return "L4T Unknown"

    def _get_nvidia_smi_identity(self) -> dict[str, Optional[str]]:
        output = self._run_command(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,uuid",
                "--format=csv,noheader,nounits",
            ]
        )
        if not output:
            return {}

        fields = [field.strip() for field in output.splitlines()[0].split(",")]
        keys = ("name", "driver_version", "uuid")
        return {
            key: value
            for key, value in zip(keys, fields)
            if value and value != "[N/A]"
        }

    @staticmethod
    def _format_driver_version(l4t_version: str, nvidia_driver_version: Optional[str]) -> str:
        if nvidia_driver_version:
            return f"{nvidia_driver_version} / {l4t_version}"
        return l4t_version

    def _get_cuda_version(self) -> str:
        output = self._run_command(["nvcc", "--version"])
        if output:
            match = re.search(r"release (\d+\.\d+)", output)
            if match:
                return match.group(1)

        version_json = self._read_sys_file("/usr/local/cuda/version.json")
        if version_json:
            try:
                version = json.loads(version_json).get("cuda", {}).get("version")
            except json.JSONDecodeError:
                version = None
            if version:
                major_minor = re.match(r"(\d+\.\d+)", version)
                return major_minor.group(1) if major_minor else version

        version_txt = self._read_sys_file("/usr/local/cuda/version.txt")
        if version_txt:
            match = re.search(r"(\d+\.\d+)", version_txt)
            if match:
                return match.group(1)

        return "Unknown"

    def _get_gpu_utilization(self) -> Optional[int]:
        for load_path in self.GPU_LOAD_PATHS:
            load = self._read_sys_file(load_path)
            if load is None:
                continue
            try:
                return max(0, min(int(float(load) / 10.0), 100))
            except ValueError:
                continue
        return None

    def _get_memory_info(self) -> tuple[Optional[float], Optional[float], Optional[float]]:
        content = self._read_sys_file("/proc/meminfo", "")
        mem_total = None
        mem_available = None

        for line in content.splitlines():
            if line.startswith("MemTotal:"):
                mem_total = int(line.split()[1]) / 1024
            elif line.startswith("MemAvailable:"):
                mem_available = int(line.split()[1]) / 1024

        if mem_total is None or mem_available is None:
            return None, None, None
        return mem_total, mem_total - mem_available, mem_available

    def _get_power_usage(self) -> Optional[float]:
        rails = self._read_ina3221_rails()
        for label in ("VDD_GPU", "VDD_CPU_GPU_CV", "GPU", "VDD_IN"):
            power_mw = rails.get(label)
            if power_mw is not None:
                return round(power_mw / 1000.0, 1)
        return None

    def _read_ina3221_rails(self) -> dict[str, int]:
        rails = {}
        for hwmon_path in glob.glob(os.path.join(self.HWMON_PATH, "hwmon*")):
            name = self._read_sys_file(os.path.join(hwmon_path, "name"), "")
            if "ina3221" not in name.lower():
                continue

            for label_file in glob.glob(os.path.join(hwmon_path, "in*_label")):
                match = re.search(r"in(\d+)_label$", label_file)
                if not match:
                    continue
                channel = match.group(1)
                label = self._read_sys_file(label_file, "")
                voltage = self._read_int_file(os.path.join(hwmon_path, f"in{channel}_input"))
                current = self._read_int_file(os.path.join(hwmon_path, f"curr{channel}_input"))
                if label and voltage is not None and current is not None:
                    rails[label] = voltage * current // 1000
        return rails

    def _get_gpu_temperature(self) -> Optional[int]:
        for zone_path in glob.glob(os.path.join(self.THERMAL_ZONE_PATH, "thermal_zone*")):
            zone_type = self._read_sys_file(os.path.join(zone_path, "type"), "")
            if "gpu" not in zone_type.lower() and "gv11b" not in zone_type.lower():
                continue
            temp = self._read_int_file(os.path.join(zone_path, "temp"))
            if temp is not None:
                return int(temp / 1000)
        return None

    def _get_fan_info(self) -> tuple[Optional[int], Optional[int]]:
        fan_percent = None
        fan_rpm = None

        for hwmon_path in glob.glob(os.path.join(self.HWMON_PATH, "hwmon*")):
            name = self._read_sys_file(os.path.join(hwmon_path, "name"), "").lower()
            if name == "pwmfan":
                pwm = self._read_int_file(os.path.join(hwmon_path, "pwm1"))
                if pwm is not None:
                    fan_percent = max(0, min(int(pwm / 255 * 100), 100))
            elif "tach" in name:
                fan_rpm = self._read_int_file(os.path.join(hwmon_path, "rpm"))

        return fan_percent, fan_rpm

    def _get_gpu_clock_mhz(self) -> Optional[int]:
        return self._read_devfreq_mhz("cur_freq")

    def _get_power_limit(self) -> Optional[float]:
        output = self._run_command(["nvpmodel", "-q"])
        if not output:
            return None

        match = re.search(r"NV Power Mode:\s*([^\n]+)", output)
        if not match:
            return None

        mode = match.group(1)
        watts = re.match(r"(\d+(?:\.\d+)?)W$", mode)
        if watts:
            return float(watts.group(1))
        return None

    def _get_emc_clock_mhz(self) -> Optional[int]:
        emc_paths = (
            "/sys/kernel/debug/bpmp/debug/clk/emc/rate",
        )
        for path in emc_paths:
            value = self._read_int_file(path)
            if value is not None and value > 0:
                return int(value / 1_000_000)
        return None

    def _read_devfreq_mhz(self, filename: str) -> Optional[int]:
        for devfreq_path in self.GPU_DEVFREQ_PATHS:
            value = self._read_int_file(os.path.join(devfreq_path, filename))
            if value is not None and value > 0:
                return int(value / 1_000_000)
        return None

    def _get_ecc_errors(self) -> Optional[int]:
        total = 0
        found = False
        for platform_path in self.GPU_PLATFORM_PATHS:
            for path in glob.glob(os.path.join(platform_path, "*ecc*count")):
                value = self._read_int_file(path)
                if value is not None:
                    total += value
                    found = True
        return total if found else None

    def _read_current_user_processes(self) -> list[GPUProcessStats]:
        processes = []
        for pid_text in os.listdir("/proc"):
            if not pid_text.isdigit():
                continue
            pid = int(pid_text)
            proc_path = os.path.join("/proc", pid_text)
            try:
                if os.stat(proc_path).st_uid != self.current_uid:
                    continue
            except OSError:
                continue
            if not self._process_has_gpu_fd(pid_text):
                continue
            process = self._build_process_stats(pid)
            if process is not None:
                processes.append(process)
        return sorted(processes, key=lambda process: process.pid)

    def _process_has_gpu_fd(self, pid_text: str) -> bool:
        fd_path = os.path.join("/proc", pid_text, "fd")
        try:
            fd_names = os.listdir(fd_path)
        except OSError:
            return False

        for fd_name in fd_names:
            try:
                target = os.readlink(os.path.join(fd_path, fd_name))
            except OSError:
                continue
            if target in self.GPU_PROCESS_DEVICES:
                return True
        return False

    def _build_process_stats(self, pid: int) -> Optional[GPUProcessStats]:
        try:
            process = psutil.Process(pid)
            username = process.username()
            name = process.name()
            cmdline = process.cmdline()
        except (psutil.Error, OSError):
            return None

        command_summary = " ".join(part for part in cmdline if part) if cmdline else None
        return GPUProcessStats(
            pid=pid,
            process_type="jetson",
            username=username,
            name=name,
            command_summary=command_summary,
            used_memory_mb=None,
        )

    def _read_int_file(self, path: str) -> Optional[int]:
        value = self._read_sys_file(path)
        if value is None:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    @staticmethod
    def _format_system_uptime() -> str:
        try:
            with open("/proc/uptime", "r") as file:
                seconds = int(float(file.read().split()[0]))
        except (OSError, ValueError, IndexError):
            seconds = 0

        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        if days:
            return f"{days}d {hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    @staticmethod
    def _get_cuda_cc(device_name: str) -> str:
        device_name_lower = device_name.lower()

        if "orin" in device_name_lower:
            return "8.7"
        if "xavier" in device_name_lower or "agx" in device_name_lower:
            return "7.2"
        if "tx2" in device_name_lower:
            return "6.2"
        if "nano" in device_name_lower or "tx1" in device_name_lower:
            return "5.3"

        return "Unknown"

    @staticmethod
    def is_jetson_device() -> bool:
        """Detect whether the current device is a Jetson device."""
        if os.path.exists("/etc/nv_tegra_release"):
            return True

        if os.path.exists("/proc/device-tree/model"):
            try:
                with open("/proc/device-tree/model", "r") as file:
                    model = file.read().lower()
            except OSError:
                return False
            return "jetson" in model or ("nvidia" in model and "tegra" in model)

        return False
