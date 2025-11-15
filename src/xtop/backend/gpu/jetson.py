import os
import re
import time


class GPUStats:
    """Statistics class, maintaining the same interface as nvidia.py"""
    def __init__(self, gpu_id: int, name: str, driver_version: str, cuda_version: str, cuda_cc: str):
        self.gpu_id: int = gpu_id
        self.name: str = name
        self.driver_version: str = driver_version
        self.cuda_version: str = cuda_version
        self.cuda_cc: str = cuda_cc
        self.utilization = None
        self.memory_used = None
        self.memory_total = None
        self.memory_free = None
        self.power_usage = None
        self.temperature = None
        self.fan_speed = None
        self.fan_speed_rpm = None

    def update(self, utilization, memory_used, memory_total, memory_free, power_usage, temperature, fan_speed, fan_speed_rpm):
        self.utilization = utilization
        self.memory_used = memory_used
        self.memory_total = memory_total
        self.memory_free = memory_free
        self.power_usage = power_usage
        self.temperature = temperature
        self.fan_speed = fan_speed
        self.fan_speed_rpm = fan_speed_rpm

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


class JetsonGPU:
    """Jetson GPU monitoring backend - directly reads from /sys and /proc filesystems"""
    
    # Common paths for Tegra devices
    TEGRA_GPU_LOAD_PATH = "/sys/devices/gpu.0/load"
    TEGRA_GPU_FREQ_PATH = "/sys/devices/gpu.0/devfreq/17000000.gv11b/cur_freq"
    TEGRA_EMC_FREQ_PATH = "/sys/kernel/actmon_avg_activity/avg_actv"
    THERMAL_ZONE_PATH = "/sys/class/thermal"
    HWMON_PATH = "/sys/class/hwmon"
    IIO_PATH = "/sys/bus/iio/devices"
    
    def __init__(self):
        self.gpu_number: int = 1
        self.gpus: list[GPUStats] = []
        self.start: bool = False
        
        # State for calculating GPU utilization
        self._last_gpu_time = 0
        self._last_total_time = 0
        self._last_timestamp = 0
        
    def init(self):
        """Initializes Jetson GPU monitoring"""
        # Get device information
        device_name = self._get_device_name()
        driver_version = self._get_l4t_version()
        cuda_version = self._get_cuda_version()
        cuda_cc = self._get_cuda_cc(device_name)
        
        # Create a single GPU statistics object
        gpu = GPUStats(0, device_name, driver_version, cuda_version, cuda_cc)
        self.gpus.append(gpu)
        
        # Initialize timestamp
        self._last_timestamp = time.time()
        
        self.start = True
    
    def shutdown(self):
        """Shuts down Jetson GPU monitoring"""
        self.start = False
    
    def update(self):
        """Updates GPU statistics"""
        if not self.start:
            return
        
        gpu = self.gpus[0]
        
        # Get GPU utilization
        utilization = self._get_gpu_utilization()
        
        # Get memory information (using system RAM)
        mem_total, mem_used, mem_free = self._get_memory_info()
        
        # Get power information
        power_usage = self._get_power_usage()
        
        # Get temperature
        temperature = self._get_gpu_temperature()
        
        # Get fan information
        fan_speed, fan_speed_rpm = self._get_fan_info()
        
        # Update statistics
        gpu.update(
            utilization=utilization,
            memory_used=mem_used,
            memory_total=mem_total,
            memory_free=mem_free,
            power_usage=power_usage,
            temperature=temperature,
            fan_speed=fan_speed,
            fan_speed_rpm=fan_speed_rpm
        )
    
    def _read_sys_file(self, path: str, default=None):
        """Safely reads a system file"""
        try:
            with open(path, 'r') as f:
                return f.read().strip()
        except:
            return default
    
    def _get_device_name(self) -> str:
        """Gets the Jetson device name"""
        # Try reading from device-tree
        model_path = "/proc/device-tree/model"
        model = self._read_sys_file(model_path, "")
        if model:
            # Remove trailing null character
            model = model.rstrip('\x00')
            return model
        
        # Try reading from other locations
        compatible_path = "/proc/device-tree/compatible"
        compatible = self._read_sys_file(compatible_path, "")
        if "jetson" in compatible.lower():
            # Parse the compatible string
            parts = compatible.split('\x00')
            for part in parts:
                if 'jetson' in part.lower():
                    return part
        
        return "NVIDIA Jetson"
    
    def _get_l4t_version(self) -> str:
        """Gets the L4T (Linux for Tegra) version"""
        nv_tegra_path = "/etc/nv_tegra_release"
        content = self._read_sys_file(nv_tegra_path, "")
        
        if content:
            # Parse format like "# R35 (release), REVISION: 4.1"
            match = re.search(r'R(\d+).*?REVISION:\s*([\d.]+)', content)
            if match:
                return f"L4T {match.group(1)}.{match.group(2)}"
        
        return "L4T Unknown"
    
    def _get_cuda_version(self) -> str:
        """Gets the CUDA version"""
        # Try getting from nvcc
        try:
            import subprocess
            result = subprocess.run(['nvcc', '--version'], 
                                  capture_output=True, text=True, timeout=1)
            if result.returncode == 0:
                match = re.search(r'release (\d+\.\d+)', result.stdout)
                if match:
                    return match.group(1)
        except:
            pass
        
        # Try reading version from CUDA path
        cuda_version_paths = [
            "/usr/local/cuda/version.txt",
            "/usr/local/cuda/version.json"
        ]
        
        for path in cuda_version_paths:
            content = self._read_sys_file(path)
            if content:
                match = re.search(r'(\d+\.\d+)', content)
                if match:
                    return match.group(1)
        
        return "Unknown"
    
    def _get_gpu_utilization(self) -> int:
        """Gets GPU utilization - implemented in the style of jtop

        """
        # Check multiple possible load file paths
        load_paths = [
            "/sys/devices/platform/gpu.0/load",
            "/sys/devices/platform/17000000.gpu/load",
            "/sys/devices/gpu.0/load",
            "/sys/class/devfreq/17000000.gpu/cur_freq",
        ]
        
        for load_path in load_paths:
            if not os.path.exists(load_path):
                continue
            if not os.access(load_path, os.R_OK):
                continue
                
            load = self._read_sys_file(load_path)
            if load:
                try:
                    # jtop logic: load value is 0-1000, directly divide by 10.0
                    # to get a percentage from 0.0-100.0
                    return int(float(load) / 10.0)
                except ValueError:
                    pass
        
        return 0
    
    def _get_memory_info(self) -> tuple:
        """Gets memory information (MB)"""
        meminfo_path = "/proc/meminfo"
        content = self._read_sys_file(meminfo_path, "")
        
        if content:
            mem_total = 0
            mem_available = 0
            
            for line in content.split('\n'):
                if line.startswith('MemTotal:'):
                    mem_total = int(line.split()[1]) / 1024  # KB to MB
                elif line.startswith('MemAvailable:'):
                    mem_available = int(line.split()[1]) / 1024
            
            if mem_total > 0:
                mem_free = mem_available
                mem_used = mem_total - mem_available
                return mem_total, mem_used, mem_free
        
        return 0.0, 0.0, 0.0
    
    def _get_power_usage(self) -> float:
        """Gets power consumption (W) - based on the correct implementation in try.py
        
        INA3221 sensor: volt(mV) * curr(mA) / 1000 = power(mW)
        """
        # INA3221 path for Orin Nano
        sensor_path = "/sys/bus/i2c/devices/1-0040/hwmon/hwmon1"
        if not os.path.isdir(sensor_path):
            # Fallback: try to find any hwmon
            import glob
            hwmon_paths = glob.glob("/sys/bus/i2c/devices/*/hwmon/hwmon*")
            found = False
            for path in hwmon_paths:
                name_file = os.path.join(path, "name")
                if os.path.exists(name_file):
                    try:
                        with open(name_file, 'r') as f:
                            if 'ina3221' in f.read().strip().lower():
                                sensor_path = path
                                found = True
                                break
                    except:
                        pass
            if not found:
                sensor_path = None

        if not sensor_path:
            return 0.0

        total_power_mw = 0
        rails = {}
        
        # Orin Nano INA3221 has 3 channels
        for channel in range(1, 4):
            try:
                # Read label
                label_file = os.path.join(sensor_path, f"in{channel}_label")
                if not os.path.exists(label_file):
                    continue
                
                with open(label_file, 'r') as f:
                    label = f.read().strip()
                
                # Read voltage (mV)
                volt_file = os.path.join(sensor_path, f"in{channel}_input")
                volt = int(self._read_sys_file(volt_file, 0))
                
                # Read current (mA)
                curr_file = os.path.join(sensor_path, f"curr{channel}_input")
                curr = int(self._read_sys_file(curr_file, 0))
                
                # Calculate power (mW)
                power = (volt * curr) // 1000
                
                rails[label] = { 'power': power }
                
                # If it's the main power rail (VDD_IN), use it as total power
                if label == "VDD_IN":
                    total_power_mw = power
                    break  # Stop accumulating once main power is found
            
            except Exception:
                continue
        
        # If VDD_IN is not found, sum all rails
        if total_power_mw == 0 and rails:
            total_power_mw = sum(rail['power'] for rail in rails.values())

        # Convert to W
        return round(total_power_mw / 1000.0, 1) if total_power_mw > 0 else 0.0
    
    def _get_gpu_temperature(self) -> int:
        """Gets GPU temperature (°C)"""
        if not os.path.exists(self.THERMAL_ZONE_PATH):
            return 0
        
        try:
            for zone in os.listdir(self.THERMAL_ZONE_PATH):
                zone_path = os.path.join(self.THERMAL_ZONE_PATH, zone)
                type_path = os.path.join(zone_path, "type")
                temp_path = os.path.join(zone_path, "temp")
                
                zone_type = self._read_sys_file(type_path, "")
                
                # Find GPU-related thermal zones
                if any(keyword in zone_type.lower() for keyword in ['gpu', 'gv11b', 'thermal']):
                    temp = self._read_sys_file(temp_path)
                    if temp:
                        try:
                            # Usually in milli-degrees
                            return int(float(temp) / 1000)
                        except:
                            pass
            
            # If no GPU temperature is found, return the first available temperature
            zones = os.listdir(self.THERMAL_ZONE_PATH)
            if zones:
                first_zone = zones[0]
                temp_path = os.path.join(self.THERMAL_ZONE_PATH, first_zone, "temp")
                temp = self._read_sys_file(temp_path)
                if temp:
                    try:
                        return int(float(temp) / 1000)
                    except:
                        pass
        except:
            pass
        
        return 0
    
    def _get_fan_info(self) -> tuple:
        """Gets fan information"""
        # Jetson fans are usually under hwmon or specific paths
        fan_paths = [
            "/sys/devices/pwm-fan/target_pwm",
            "/sys/devices/pwm-fan/cur_pwm",
            "/sys/class/hwmon/hwmon0/pwm1",
            "/sys/class/hwmon/hwmon1/pwm1",
        ]
        
        for path in fan_paths:
            pwm = self._read_sys_file(path)
            if pwm:
                try:
                    pwm_val = int(pwm)
                    # PWM is usually 0-255
                    fan_percent = int((pwm_val / 255) * 100)
                    return fan_percent, None
                except:
                    pass
        
        # Most Jetsons are fanless designs
        return None, None
    
    @staticmethod
    def _get_cuda_cc(device_name: str) -> str:
        """Infers CUDA Compute Capability from the device name"""
        device_name_lower = device_name.lower()
        
        if 'orin' in device_name_lower:
            return "8.7"
        elif 'xavier' in device_name_lower or 'agx' in device_name_lower:
            return "7.2"
        elif 'tx2' in device_name_lower:
            return "6.2"
        elif 'nano' in device_name_lower or 'tx1' in device_name_lower:
            return "5.3"
        
        return "Unknown"
    
    @staticmethod
    def is_jetson_device() -> bool:
        """Detects if the current device is a Jetson device"""
        # Check for nv_tegra_release file
        if os.path.exists('/etc/nv_tegra_release'):
            return True
        
        # Check device-tree model
        if os.path.exists('/proc/device-tree/model'):
            try:
                with open('/proc/device-tree/model', 'r') as f:
                    model = f.read().lower()
                    if 'jetson' in model or 'nvidia' in model and 'tegra' in model:
                        return True
            except:
                pass
        
        return False
