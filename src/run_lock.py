import fcntl
import os


class RunLock:
    def __init__(self, name):
        os.makedirs("data", exist_ok=True)
        self.path = os.path.join("data", f"{name}.lock")
        self.file = None

    def __enter__(self):
        self.file = open(self.path, "a+")
        try:
            fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"{self.path} is already locked") from exc

        self.file.seek(0)
        self.file.truncate()
        self.file.write(str(os.getpid()))
        self.file.flush()
        return self

    def __exit__(self, exc_type, exc, traceback):
        if self.file is not None:
            fcntl.flock(self.file, fcntl.LOCK_UN)
            self.file.close()
