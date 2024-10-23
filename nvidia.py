import pynvml


class GPUStats:
    def __init__(self, gpu_id: int, name: str):
        self.gpu_id: int = gpu_id
        self.name: str = name
        self.utilization = None
        self.memory_used = None
        self.memory_total = None
        self.memory_free = None

    def update(self, utilization, memory_used, memory_total, memory_free):
        self.utilization = utilization
        self.memory_used = memory_used
        self.memory_total = memory_total
        self.memory_free = memory_free

    def getTitle(self):
        return f"Device: {self.gpu_id} {self.name}"

    def getData(self):
        return f"Utilization: {self.utilization}% Memory Used: {self.memory_used:.2f}MB / {self.memory_total:.2f}MB"


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
            gpu = GPUStats(i, name)
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
            mem_used = mem_info.used / (1024 ** 2)
            mem_total = mem_info.total / (1024 ** 2)
            mem_free = mem_info.free / (1024 ** 2)
            gpu.update(utilization, mem_used, mem_total, mem_free)

