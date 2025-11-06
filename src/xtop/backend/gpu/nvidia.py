import pynvml


class GPUStats:
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


class NvidiaGPU:
    def __init__(self):
        self.gpu_number: int = 0
        self.gpus: list[GPUStats] = []
        self.start: bool = False

    def init(self):
        pynvml.nvmlInit()
        self.gpu_number = pynvml.nvmlDeviceGetCount()
        for i in range(self.gpu_number):
            name = pynvml.nvmlDeviceGetName(pynvml.nvmlDeviceGetHandleByIndex(i))
            driver_version = pynvml.nvmlSystemGetDriverVersion()
            cuda_version = self.__convertCudaDriverVersion(pynvml.nvmlSystemGetCudaDriverVersion())
            cuda_cc = self.__convertCudaCC(pynvml.nvmlDeviceGetCudaComputeCapability(pynvml.nvmlDeviceGetHandleByIndex(i)))
            gpu = GPUStats(i, name, driver_version, cuda_version, cuda_cc)
            self.gpus.append(gpu)
        self.start = True

    def shutdown(self):
        pynvml.nvmlShutdown()
        self.start = False

    def update(self):
        for gpu in self.gpus:
            handle = pynvml.nvmlDeviceGetHandleByIndex(gpu.gpu_id)
            utilization = pynvml.nvmlDeviceGetUtilizationRates(handle).gpu
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            temperature = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)

            try:
                fan_speed = pynvml.nvmlDeviceGetFanSpeed(handle)
            except pynvml.NVMLError:
                fan_speed = None
            try:
                fan_speed_rpm = pynvml.nvmlDeviceGetFanSpeedRPM(handle)
            except pynvml.NVMLError:
                fan_speed_rpm = None

            power_usage = round(pynvml.nvmlDeviceGetPowerUsage(handle) / 1000, 1)  # function return mW.
            mem_used = mem_info.used / (1024 ** 2)
            mem_total = mem_info.total / (1024 ** 2)
            mem_free = mem_info.free / (1024 ** 2)
            gpu.update(utilization, mem_used, mem_total, mem_free, power_usage, temperature, fan_speed, fan_speed_rpm)

    @staticmethod
    def __convertCudaDriverVersion(version: int) -> str:
        major = version // 1000
        minor = (version % 1000) // 10
        return f"{major}.{minor}"

    @staticmethod
    def __convertCudaCC(cuda_cc: tuple) -> str:
        return f"{cuda_cc[0]}.{cuda_cc[1]}"
