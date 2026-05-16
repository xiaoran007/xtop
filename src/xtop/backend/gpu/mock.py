import getpass
import math
import os
import time

from .models import GPUProcessStats, GPUStats


class MockNvidiaGPU:
    """Simulated Nvidia backend for local TUI development."""

    def __init__(self, gpu_number: int = 4):
        self.gpu_number = gpu_number
        self.gpus: list[GPUStats] = []
        self.start = False
        self.current_username = getpass.getuser()
        self._started_at = time.monotonic()

    def init(self):
        self.gpus = [
            GPUStats(
                gpu_id=index,
                name=f"Mock RTX {6000 + index * 100} 48GB Max-Q Blackwell Server Edition",
                driver_version="555.99",
                cuda_version="12.5",
                cuda_cc="9.0",
                uuid=f"GPU-mock-{index:04d}-xtop",
            )
            for index in range(self.gpu_number)
        ]
        self.start = True
        self.update()

    def shutdown(self):
        self.start = False

    def update(self):
        if not self.start:
            return

        elapsed = time.monotonic() - self._started_at
        for gpu in self.gpus:
            phase = elapsed + gpu.gpu_id * 1.7
            utilization = int(50 + 38 * math.sin(phase / 2.4) + 9 * math.sin(phase * 1.6))
            utilization = max(0, min(100, utilization))

            memory_total = 49152.0 if gpu.gpu_id % 2 == 0 else 24576.0
            memory_percent = max(8.0, min(94.0, utilization * 0.72 + 12 * math.sin(phase / 4.0) + 10))
            memory_used = memory_total * memory_percent / 100.0
            memory_free = memory_total - memory_used
            power_limit = 450.0 if memory_total > 30000 else 300.0
            power_usage = round(45.0 + power_limit * utilization / 118.0, 1)
            temperature = int(39 + utilization * 0.42)
            fan_speed = min(88, max(20, int(25 + utilization * 0.58)))

            gpu.update(
                utilization=utilization,
                memory_used=memory_used,
                memory_total=memory_total,
                memory_free=memory_free,
                power_usage=power_usage,
                temperature=temperature,
                fan_speed=fan_speed,
                fan_speed_rpm=900 + fan_speed * 28,
                power_limit=power_limit,
                p_state="P0" if utilization > 65 else "P2",
                graphics_clock_mhz=1410 + utilization * 10,
                sm_clock_mhz=1380 + utilization * 10,
                memory_clock_mhz=9501,
                pcie_tx_kbps=int(256 + utilization * 31 + gpu.gpu_id * 128),
                pcie_rx_kbps=int(512 + utilization * 49 + gpu.gpu_id * 192),
                processes=self._build_processes(gpu.gpu_id, memory_used, utilization),
                pcie_gen="Gen4",
                pcie_link_width="x16",
                uptime=self._format_mock_uptime(elapsed),
                ecc_errors=0,
                performance_cap="None",
            )

    @staticmethod
    def _format_mock_uptime(elapsed: float) -> str:
        seconds = max(0, int(elapsed))
        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        if days:
            return f"{days}d {hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def _build_processes(self, gpu_id: int, memory_used: float, utilization: int) -> list[GPUProcessStats]:
        process_count = 1 + int(utilization > 45) + int(utilization > 75)
        names = ["python", "torchrun", "python"]
        commands = [
            "python train.py --config experiments/llm.yaml",
            "torchrun --nproc-per-node 4 finetune.py",
            "python serve.py --model checkpoint/latest",
        ]
        per_process_memory = memory_used / max(process_count, 1)
        base_pid = os.getpid() + gpu_id * 100

        return [
            GPUProcessStats(
                pid=base_pid + index + 1,
                process_type="compute",
                username=self.current_username,
                name=names[index],
                command_summary=commands[index],
                used_memory_mb=max(256.0, per_process_memory * (1.0 - index * 0.18)),
            )
            for index in range(process_count)
        ]
