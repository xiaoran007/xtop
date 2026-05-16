from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GPUProcessStats:
    pid: int
    process_type: str
    username: Optional[str] = None
    name: Optional[str] = None
    command_summary: Optional[str] = None
    used_memory_mb: Optional[float] = None


@dataclass
class GPUStats:
    gpu_id: int
    name: str
    driver_version: str
    cuda_version: str
    cuda_cc: str
    uuid: Optional[str] = None
    utilization: Optional[int] = None
    memory_used: Optional[float] = None
    memory_total: Optional[float] = None
    memory_free: Optional[float] = None
    power_usage: Optional[float] = None
    temperature: Optional[int] = None
    fan_speed: Optional[int] = None
    fan_speed_rpm: Optional[int] = None
    power_limit: Optional[float] = None
    p_state: Optional[str] = None
    graphics_clock_mhz: Optional[int] = None
    sm_clock_mhz: Optional[int] = None
    memory_clock_mhz: Optional[int] = None
    pcie_tx_kbps: Optional[int] = None
    pcie_rx_kbps: Optional[int] = None
    pcie_gen: Optional[str] = None
    pcie_link_width: Optional[str] = None
    uptime: Optional[str] = None
    ecc_errors: Optional[int] = None
    performance_cap: Optional[str] = None
    processes: list[GPUProcessStats] = field(default_factory=list)
    current_user_process_count: int = 0

    def update(
        self,
        *,
        utilization,
        memory_used,
        memory_total,
        memory_free,
        power_usage,
        temperature,
        fan_speed,
        fan_speed_rpm,
        power_limit,
        p_state,
        graphics_clock_mhz,
        sm_clock_mhz,
        memory_clock_mhz,
        pcie_tx_kbps,
        pcie_rx_kbps,
        processes,
        pcie_gen=None,
        pcie_link_width=None,
        uptime=None,
        ecc_errors=None,
        performance_cap=None,
    ):
        self.utilization = utilization
        self.memory_used = memory_used
        self.memory_total = memory_total
        self.memory_free = memory_free
        self.power_usage = power_usage
        self.temperature = temperature
        self.fan_speed = fan_speed
        self.fan_speed_rpm = fan_speed_rpm
        self.power_limit = power_limit
        self.p_state = p_state
        self.graphics_clock_mhz = graphics_clock_mhz
        self.sm_clock_mhz = sm_clock_mhz
        self.memory_clock_mhz = memory_clock_mhz
        self.pcie_tx_kbps = pcie_tx_kbps
        self.pcie_rx_kbps = pcie_rx_kbps
        self.pcie_gen = pcie_gen
        self.pcie_link_width = pcie_link_width
        self.uptime = uptime
        self.ecc_errors = ecc_errors
        self.performance_cap = performance_cap
        self.processes = processes
        self.current_user_process_count = len(processes)

    def getTitle(self):
        return f"Device {self.gpu_id}: {self.name} (Driver: {self.driver_version}, CUDA {self.cuda_version}, CUDA CC {self.cuda_cc})"

    def getUtilization(self):
        return f"Utilization: {self.utilization}% Memory Used: {self.memory_used:.2f}MB / {self.memory_total:.2f}MB"

    def getPower(self):
        if self.fan_speed is not None and self.fan_speed_rpm is not None:
            fan_info = f"Fan Speed: {self.fan_speed_rpm} RPM ({self.fan_speed}%)"
        else:
            fan_info = "Fan: N/A (Fanless GPU)"
        return f"Power Usage: {self.power_usage}W Temperature: {self.temperature}°C {fan_info}"
