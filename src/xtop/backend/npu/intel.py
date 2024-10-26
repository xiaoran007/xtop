from pypci import PCI
import time


class NPUStats:
    def __init__(self, pci_device, npu_id: int, name: str):
        self.PCI_Device = pci_device
        self.npu_id: int = npu_id
        self.name: str = name
        self.utilization = None
        self.memory_used = None
        self.memory_total = None
        self.memory_free = None
        self.last_busy_time_us = 0
        self.last_busy_time_timestamp = 0

    def update(self, utilization, memory_used, memory_total, memory_free):
        self.utilization = utilization
        self.memory_used = memory_used
        self.memory_total = memory_total
        self.memory_free = memory_free

    def getTitle(self):
        return f"Device: {self.npu_id} {self.name}"

    def getData(self):
        return f"Utilization: {self.utilization}%"


class IntelNPU:
    def __init__(self):
        self.npu_number: int = 0
        self.npus: list[NPUStats] = []
        self.start: bool = False

    def init(self):
        npu_devices = PCI().FindAllNPU()
        self.npu_number = len(npu_devices)
        for i in range(self.npu_number):
            self.npus.append(NPUStats(npu_devices[i], i, f"{npu_devices[i].vendor_name} {npu_devices[i].device_name}"))

    def shutdown(self):
        pass

    def update(self):
        for device in self.npus:
            device.utilization = self.__getUtilization(device)

    def __getUtilization(self, device: NPUStats):
        new_timestamp = int(time.time() * 1000)
        try:
            new_busy_time = int(self.__read_device_int(device.PCI_Device.path, "npu_busy_time_us"))
        except FileNotFoundError:
            raise RuntimeError("Unable to read busy time")

        delta_timestamp = new_timestamp - device.last_busy_time_timestamp
        delta_busy_time = new_busy_time - device.last_busy_time_us

        device.last_busy_time_timestamp = new_timestamp
        device.last_busy_time_us = new_busy_time
        utilization = (delta_busy_time / delta_timestamp) / 1000.0 if delta_timestamp > 0 else 0.0

        return round(utilization, 2)

    @staticmethod
    def __read_device_int(device_path, filename):
        path = device_path / filename
        with open(path) as f:
            return int(f.read().strip())
