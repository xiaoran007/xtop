"""
macOS CPU monitoring backend.
Uses fake data for testing purposes.
"""
import random


class CPUStats:
    """CPU statistics data class."""
    
    def __init__(self, cpu_id: int, name: str, cores: int, threads: int):
        self.cpu_id: int = cpu_id
        self.name: str = name
        self.cores: int = cores
        self.threads: int = threads
        self.utilization = None
        self.frequency = None
        self.temperature = None
        self.power_usage = None
        # Per-core utilization (list)
        self.core_utilization = None

    def update(self, utilization, frequency, temperature, power_usage, core_utilization):
        """Update CPU statistics."""
        self.utilization = utilization
        self.frequency = frequency
        self.temperature = temperature
        self.power_usage = power_usage
        self.core_utilization = core_utilization

    def getTitle(self):
        """Get CPU title string."""
        return f"CPU {self.cpu_id}: {self.name} ({self.cores} cores, {self.threads} threads)"

    def getUtilization(self):
        """Get utilization string."""
        return f"Utilization: {self.utilization}% Frequency: {self.frequency:.2f}GHz"

    def getPower(self):
        """Get power and temperature string."""
        return f"Power Usage: {self.power_usage}W Temperature: {self.temperature}°C"


class AppleCPU:
    """Apple CPU monitoring class using fake data."""
    
    def __init__(self):
        self.cpu_number: int = 0
        self.cpus: list[CPUStats] = []
        self.start: bool = False
        # For generating realistic fake data
        self._base_util = 30.0
        self._base_freq = 3.2
        self._base_temp = 50.0
        self._base_power = 15.0

    def init(self):
        """Initialize CPU monitoring with fake data."""
        # Simulate a single CPU with multiple cores
        self.cpu_number = 1
        
        # Fake CPU info (e.g., Apple M-series or Intel)
        cpu = CPUStats(
            cpu_id=0,
            name="Apple M2 Pro",  # Or could be "Intel Core i7-9750H"
            cores=10,  # 6 performance + 4 efficiency cores
            threads=10
        )
        self.cpus.append(cpu)
        self.start = True

    def shutdown(self):
        """Shutdown CPU monitoring."""
        self.start = False

    def update(self):
        """Update CPU statistics with fake data."""
        for cpu in self.cpus:
            # Generate fake but realistic data with some variation
            utilization = max(0, min(100, self._base_util + random.uniform(-10, 20)))
            frequency = max(0.5, self._base_freq + random.uniform(-0.5, 0.8))
            temperature = max(30, self._base_temp + random.uniform(-5, 15))
            power_usage = round(max(5, self._base_power + random.uniform(-5, 15)), 1)
            
            # Generate per-core utilization
            core_utilization = []
            for i in range(cpu.cores):
                # Some cores might be more active than others
                core_util = max(0, min(100, utilization + random.uniform(-20, 20)))
                core_utilization.append(round(core_util, 1))
            
            # Update with slight drift in base values for more realistic behavior
            self._base_util = max(10, min(80, self._base_util + random.uniform(-2, 2)))
            self._base_freq = max(2.0, min(3.5, self._base_freq + random.uniform(-0.1, 0.1)))
            self._base_temp = max(45, min(70, self._base_temp + random.uniform(-1, 1)))
            self._base_power = max(10, min(30, self._base_power + random.uniform(-1, 1)))
            
            cpu.update(
                round(utilization, 1),
                round(frequency, 2),
                round(temperature, 1),
                power_usage,
                core_utilization
            )
