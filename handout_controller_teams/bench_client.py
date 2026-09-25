"""Minimal WDR bench client for your server (Python 3, standard library only).

    python bench_client.py 127.0.0.1        # against: python wdr_tool.py serve-sim
    python bench_client.py <bench ip>       # against the real bench
"""
import queue
import socket
import sys
import threading


class Bench:
    def __init__(self, host, port=3333):
        self.sock = socket.create_connection((host, port), timeout=5)
        self.replies = queue.Queue()      # OK / ERR lines, in order
        self.lock = threading.Lock()      # one command in flight at a time
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        # Every line from the bench is routed by its FIRST WORD.
        f = self.sock.makefile("r", encoding="ascii", newline="\n")
        for line in f:
            line = line.strip()
            if line.startswith(("OK", "ERR")):
                self.replies.put(line)
            elif line.startswith("TEL"):
                self.on_tel(line)
            elif line.startswith("EVT"):
                self.on_evt(line)
        self.replies.put(None)            # connection closed

    def cmd(self, line, timeout=2.0):
        """Send one command and wait for its one reply."""
        with self.lock:
            self.sock.sendall((line + "\n").encode("ascii"))
            return self.replies.get(timeout=timeout)

    # Override these in your server: update the dashboard, log to your database...
    def on_tel(self, line):
        print("  telemetry:", line)

    def on_evt(self, line):
        print("  event:    ", line)


def kv(reply):
    """'OK STATUS state=RUNNING cycle=3 ...' -> {'state': 'RUNNING', 'cycle': '3', ...}"""
    return dict(t.split("=", 1) for t in reply.split()[2:] if "=" in t)


if __name__ == "__main__":
    b = Bench(sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1")
    print(b.cmd("INFO"))
    print(b.cmd("STOP"))

    frames = [[1500, 1500, 1500, 1500], [1600, 1400, 1500, 1700], [1700, 1300, 1500, 1900]]
    print(b.cmd("LOAD 10 %d" % len(frames)))
    for i, row in enumerate(frames):
        b.cmd("F %d %s" % (i, " ".join(map(str, row))))
    reply = b.cmd("COMMIT")
    assert int(reply.split("SUM=")[1]) == sum(map(sum, frames)) % 65536, "upload corrupted"
    print(reply)

    print(b.cmd("TEL 1"))
    print(b.cmd("START 5"))
    import time; time.sleep(0.5)
    s = kv(b.cmd("STATUS"))
    print("dashboard: state=%s cycle %s of %s, %d%% through this cycle"
          % (s["state"], s["cycle"], s["target"], 100 * int(s["frame"]) // int(s["frames"])))
    print(b.cmd("STOP"))
    print(b.cmd("COUNTERS"))
