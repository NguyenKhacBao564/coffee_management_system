import os
import resource
import sys
import threading
import time

import psutil


class Profiler:
    def __init__(self):
        self.process = psutil.Process()
        self.started = time.perf_counter()
        self.cpu_start = self.process.cpu_times()
        self.peak = 0
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._sample, daemon=True)
        self.thread.start()

    def _sample(self):
        while not self.stopped.is_set():
            self.peak = max(self.peak, self.process.memory_info().rss)
            self.stopped.wait(.1)

    def finish(self):
        self.stopped.set(); self.thread.join()
        wall = time.perf_counter() - self.started
        cpu = self.process.cpu_times()
        seconds = cpu.user + cpu.system - self.cpu_start.user - self.cpu_start.system
        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        peak = max(self.peak, usage if sys.platform == "darwin" else usage * 1024)
        cores = os.cpu_count() or 1
        return {"wall_seconds_including_model_init":wall, "process_cpu_seconds":seconds,
                "average_cpu_percent_one_core":seconds / wall * 100,
                "average_cpu_percent_machine_capacity":seconds / wall * 100 / cores,
                "logical_cpu_count":cores, "process_peak_rss_bytes":peak,
                "measurement_scope":"CPU/wall: model init + media processing/evidence including decoder/OpenCV threads; excludes imports, final hashing/report export and child processes. Peak RSS: OS process lifetime high-watermark (including imports) plus interval sampling; not total machine/Docker RAM"}
