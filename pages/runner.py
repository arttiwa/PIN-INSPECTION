import queue
import subprocess
import sys
import threading

from pages.config import APP_DIR, PIN_APP_PATH


class ProcessRunner:
    def __init__(self, on_log, on_done):
        self.on_log = on_log
        self.on_done = on_done
        self.process = None
        self._queue = queue.Queue()

    def is_running(self):
        return self.process is not None and self.process.poll() is None

    def start(self, mode):
        if self.is_running():
            self.on_log("Another task is already running.\n")
            return

        cmd = [sys.executable, "-u", str(PIN_APP_PATH), "--mode", mode]
        self.on_log(f"$ {' '.join(cmd)}\n")
        self.process = subprocess.Popen(
            cmd,
            cwd=str(APP_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        threading.Thread(target=self._read_output, daemon=True).start()

    def stop(self):
        if self.is_running():
            self.on_log("Stopping current task...\n")
            self.process.terminate()

    def poll(self):
        while True:
            try:
                message = self._queue.get_nowait()
            except queue.Empty:
                break
            if isinstance(message, int):
                self.on_done(message)
            else:
                self.on_log(message)

    def _read_output(self):
        if not self.process or not self.process.stdout:
            return
        for line in self.process.stdout:
            self._queue.put(line)
        self._queue.put(self.process.wait())
