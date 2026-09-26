"""Atomic, durable motor command checkpoint; contains no inferred motor motion."""
import json
import os
from pathlib import Path


class MotorJournal:
    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        if not self.path.exists():
            return None
        value = json.loads(self.path.read_text())
        if value.get("version") != 1:
            raise ValueError("Unsupported motor checkpoint; preserve it for inspection")
        return value

    def save(self, state, recovery):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w") as output:
            json.dump({"version": 1, "state": state, "recovery": recovery}, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, self.path)
        descriptor = os.open(self.path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
