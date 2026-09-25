#!/usr/bin/env python3
"""
wdr_tool.py -- Welkinrim Durability Replay: judges'/students' PC tool.

Talks WDR Protocol v1 (see PROTOCOL.md) to an ESP32 board over USB serial, or to
an in-process simulator (--port sim). Scores a board against SCORING.md.

Only third-party dependency: pyserial. It is imported lazily (only when you use a
real serial port), so `--port sim` works with a bare Python 3.8+ install.

Subcommands:
    test     <PROTOCOL.md/SCORING.md conformance scorer, out of 85>
    upload   <play a CSV flight recording onto a board>
    term     <interactive terminal>
    soak     <long-running endurance check>
    makecsv  <generate a sample flight CSV>

Run `python wdr_tool.py <subcommand> -h` for per-command help.

------------------------------------------------------------------------------
POINT SPLIT (must sum to SCORING.md's 85 automated points; see also the
CHECK TABLE printed by each level's runner function below, which documents
exactly how each level's total is divided across its individual checks):

  Level 1 Hello              10  = PING(2) + INFO(3) + UNKNOWN(2) + EVT BOOT(3)
  Level 2 Manual PWM         10  = SET works(2) + STATUS reflects(2) +
                                    bad channel->RANGE(2) + bad us->RANGE(2) +
                                    missing args->ARGS(2)
  Level 3 Profile upload     15  = round-trip(3) + SUM correct(3) +
                                    out-of-order->ARGS(3) + too-big->FULL(3) +
                                    early COMMIT->STATE(3)
  Level 4 Player             25  = state-machine transitions(6) +
                                    ERR STATE cases(5) + EVT CYCLE count(4) +
                                    EVT DONE / final STATUS(3) +
                                    cycle period +-2%(4) + TEL interval(3)
  Level 5 Counters/power-loss 20 = CLEAR works(4) + COUNTERS grows(5) +
                                    active_s selectivity(5) +
                                    reset keeps counters(6)
  Level 6 Robustness          5  = garbage line(1) + 200-char line(1) +
                                    empty line(1) + burst of 50(2)
  -------------------------------------------------------------
  Automated total            85

--level N runs ONLY level N (matches the README's per-step point column, e.g.
"test --level 3" is scored out of 15, not cumulative). A plain `test` with no
--level runs Levels 1..6 in order and totals out of 85.
------------------------------------------------------------------------------
"""

import argparse
import csv
import json
import math
import os
import queue
import sys
import tempfile
import threading
import time

# --------------------------------------------------------------------------
# Protocol constants
# --------------------------------------------------------------------------
BAUD = 115200
REPLY_TIMEOUT = 1.0     # seconds, per PROTOCOL.md section 1
LATE_REPLY_WINDOW = 3.0 # a reply later than this is treated as never coming
IDLE_US = 1500
ACTIVE_DEADBAND = 25    # us away from idle counts as "active"

# ==========================================================================
# Transport layer: a tiny interface (open/close/write_line/read_line/reset)
# implemented once for real serial ports and once for the in-process sim.
# ==========================================================================

class SerialTransport:
    """Talks to a real board over USB serial (pyserial)."""

    def __init__(self, port):
        self.port = port
        self.ser = None

    def open(self):
        import serial  # lazy import: only needed for real hardware
        ser = serial.Serial()
        ser.port = self.port
        ser.baudrate = BAUD
        ser.bytesize = 8
        ser.parity = 'N'
        ser.stopbits = 1
        ser.timeout = 0.05
        # Do NOT reset the board just by opening the port: hold DTR/RTS low
        # BEFORE open() (standard ESP32 auto-reset uses RTS=EN, DTR=IO0).
        ser.dtr = False
        ser.rts = False
        ser.open()
        self.ser = ser
        self._buf = b""
        self.closed = False

    def close(self):
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:
                pass

    def write_line(self, line):
        self.ser.write((line + "\n").encode("ascii", errors="replace"))
        self.ser.flush()

    def read_line(self, timeout):
        """Read one \\n-terminated line (","\\r" stripped), or None on timeout."""
        deadline = time.monotonic() + timeout
        while True:
            nl = self._buf.find(b"\n")
            if nl != -1:
                line = self._buf[:nl]
                self._buf = self._buf[nl + 1:]
                return line.replace(b"\r", b"").decode("ascii", errors="replace")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            self.ser.timeout = min(0.05, max(0.001, remaining))
            chunk = self.ser.read(4096)
            if chunk:
                self._buf += chunk

    def reset(self):
        """Standard ESP32 auto-reset pulse: RTS=EN, DTR=IO0. Keep IO0 high
        (DTR False) so the board boots normally, not into download mode."""
        self.ser.dtr = False
        self.ser.rts = True
        time.sleep(0.1)
        self.ser.rts = False
        self._buf = b""


class TcpTransport:
    """Talks to a board over Wi-Fi: one TCP connection, text lines.
    `closed` becomes True when the board closes the connection (EOF)."""

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.sock = None
        self.closed = False
        self._buf = b""

    def open(self):
        import socket
        self.sock = socket.create_connection((self.host, self.port), timeout=3.0)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def close(self):
        self.closed = True
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass

    def write_line(self, line):
        if self.closed:
            return
        try:
            self.sock.sendall((line + "\n").encode("ascii", errors="replace"))
        except OSError:
            self.closed = True

    def read_line(self, timeout):
        deadline = time.monotonic() + timeout
        while True:
            nl = self._buf.find(b"\n")
            if nl != -1:
                line = self._buf[:nl]
                self._buf = self._buf[nl + 1:]
                return line.replace(b"\r", b"").decode("ascii", errors="replace")
            remaining = deadline - time.monotonic()
            if remaining <= 0 or self.closed:
                return None
            self.sock.settimeout(min(0.05, max(0.001, remaining)))
            try:
                chunk = self.sock.recv(4096)
            except OSError as e:
                if "timed out" in str(e) or e.__class__.__name__ == "timeout":
                    continue
                self.closed = True
                return None
            if not chunk:
                self.closed = True  # peer closed the connection
                return None
            self._buf += chunk


class TcpUsbTransport(TcpTransport):
    """Test-only: the 'USB serial' of a `serve-sim` bench, reached over TCP.
    Selected with --serial tcp://127.0.0.1:3334. reset() power-cycles the sim."""

    def reset(self):
        self.write_line("!RESET")


class SimUsbTransport:
    """In-process sim: its 'USB serial' side (EVT BOOT, EVT IP, commands)."""

    def __init__(self, dev):
        self.dev = dev
        self.q = dev.usb_q
        self.closed = False

    def open(self):
        pass

    def close(self):
        pass

    def write_line(self, line):
        self.dev.handle(line, self)

    def read_line(self, timeout):
        try:
            return self.q.get(timeout=max(0.0, timeout))
        except queue.Empty:
            return None

    def reset(self):
        self.dev.reboot()


class SimLinkTransport:
    """In-process sim: one 'TCP client' connection to the simulated bench."""

    def __init__(self, dev):
        self.dev = dev
        self.q = queue.Queue()
        self.closed = False

    def open(self):
        if not self.dev.net_up.is_set():
            raise ConnectionRefusedError("sim bench is not on Wi-Fi yet")
        self.dev.connect_client(self)

    def close(self):
        self.closed = True
        self.dev.disconnect_client(self)

    def write_line(self, line):
        if not self.closed:
            self.dev.handle(line, self)

    def read_line(self, timeout):
        deadline = time.monotonic() + timeout
        while True:
            try:
                return self.q.get(timeout=0.05)
            except queue.Empty:
                if self.closed or time.monotonic() >= deadline:
                    return None


def open_serial_like(spec):
    """--serial value -> transport: 'COM5', '/dev/ttyUSB0', or tcp://host:port."""
    if spec.startswith("tcp://"):
        host, port = spec[6:].rsplit(":", 1)
        t = TcpUsbTransport(host, int(port))
    else:
        t = SerialTransport(spec)
    t.open()
    return t


class Bench:
    """Everything the tool knows about the board under test:
      usb  -- USB serial transport (or None): EVT BOOT, EVT IP, reset
      link -- the control link the levels talk over (TCP, or USB if no --host)
      wifi -- True if `link` is a real (or simulated) Wi-Fi connection
      r    -- ReplyReader on `link`; replaced on every reconnect."""

    def __init__(self, args):
        self.args = args
        self.usb = None
        self.sim = None
        port = getattr(args, "port", None)
        serial_spec = getattr(args, "serial", None)
        host = getattr(args, "host", None)
        if port == "sim":
            self.sim = SimDevice()
            self.sim.start()
            self.usb = SimUsbTransport(self.sim)
            self._new_link = lambda: SimLinkTransport(self.sim)
            self.wifi = True
        else:
            if port and not serial_spec:
                serial_spec = port  # --port COMx is an alias for --serial COMx
            if serial_spec:
                self.usb = open_serial_like(serial_spec)
            if host:
                tcp_port = getattr(args, "tcp_port", 3333)
                self._new_link = lambda: TcpTransport(host, tcp_port)
                self.wifi = True
            elif self.usb is not None:
                self._new_link = None
                self.wifi = False
            else:
                raise SystemExit("Give --host <board ip> and/or --serial <port> (or --port sim).")
        self.link = None
        self.connect()
        self.u = ReplyReader(self.usb) if self.usb is not None else None

    def connect(self):
        """Open a fresh control link (a new TCP client). Raises on failure."""
        if self._new_link is None:
            self.link = self.usb
        else:
            link = self._new_link()
            link.open()
            self.link = link
        self.r = ReplyReader(self.link)
        return self.r

    def drop_link(self):
        if self.wifi and self.link is not None:
            self.link.close()

    def reconnect(self, within):
        """Keep trying to connect and get an INFO reply for `within` seconds.
        Returns the INFO reply, or None."""
        deadline = time.monotonic() + within
        while time.monotonic() < deadline:
            try:
                if self.wifi:
                    self.drop_link()
                    self.connect()
                reply = self.r.send("INFO")
                if reply and reply.startswith("OK INFO"):
                    return reply
            except OSError:
                pass
            time.sleep(0.5)
        return None

    def can_reboot(self):
        return not self.args.no_reset

    def reboot(self):
        """Power-cycle the board: DTR/RTS pulse if we have USB, otherwise ask
        the human. Returns False if rebooting is not possible (--no-reset)."""
        if self.args.no_reset:
            return False
        if self.usb is not None:
            while self.usb.read_line(0.05) is not None:  # drain old lines
                pass
            self.usb.reset()
        else:
            input("\n  >>> POWER-CYCLE THE BOARD NOW (unplug and replug it), then press Enter <<< ")
        return True

    def close(self):
        if self.link is not None and self.link is not self.usb:
            self.link.close()
        if self.usb is not None:
            self.usb.close()
        if self.sim is not None:
            self.sim.stop()


# ==========================================================================
# SimDevice: the reference board. 4 channels, maxframes 8000, team=SIM.
# Counters persist across "reset" in a JSON file in the temp dir, so the
# power-loss test is meaningful even without real hardware.
# ==========================================================================

CH = 4
MAXFRAMES = 8000   # same as the reference bench
TEAM = "SIM"
STATE_FILE = os.path.join(tempfile.gettempdir(), "wdr_sim_counters.json")


def _err(code, msg=""):
    return ("ERR " + code + (" " + msg if msg else "")).rstrip()


def _to_int(s):
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


class SimDevice:
    def __init__(self):
        self.lock = threading.RLock()
        self.usb_q = queue.Queue()      # what the board prints on USB serial
        self.client = None              # the one connected TCP client (or None)
        self.net_up = threading.Event() # set once "Wi-Fi" is up after boot
        self.boot_time = time.monotonic()
        self.stop_flag = threading.Event()
        self.state = "STOPPED"
        self.us = [IDLE_US] * CH
        self.load_buf = None
        self.load_rate = None
        self.load_expected = None
        self.load_next = 0
        self.profile = None
        self.profile_len = 0
        self.profile_rate = None
        self.cycle_run = 0
        self.target = 0
        self.frame_idx = 0
        self.tel_enabled = False
        self.cycles_total = 0.0
        self.run_s_total = 0.0
        self.active_s_total = [0.0] * CH
        self.last_checkpoint = time.monotonic()
        self.last_save = time.monotonic()
        self._load_counters()

    # ---- persistence -----------------------------------------------------
    def _load_counters(self):
        try:
            with open(STATE_FILE, "r") as f:
                d = json.load(f)
            self.cycles_total = float(d.get("cycles", 0))
            self.run_s_total = float(d.get("run_s", 0))
            act = d.get("active_s", [0] * CH)
            self.active_s_total = [float(act[i]) if i < len(act) else 0.0 for i in range(CH)]
        except Exception:
            self.cycles_total = 0.0
            self.run_s_total = 0.0
            self.active_s_total = [0.0] * CH

    def save_counters(self):
        d = {
            "cycles": round(self.cycles_total),
            "run_s": round(self.run_s_total),
            "active_s": [round(x) for x in self.active_s_total],
        }
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(d, f)
        os.replace(tmp, STATE_FILE)
        self.last_save = time.monotonic()

    # ---- accounting --------------------------------------------------------
    def _checkpoint(self):
        now = time.monotonic()
        if self.state == "RUNNING":
            dt = now - self.last_checkpoint
            self.run_s_total += dt
            for ch in range(CH):
                if abs(self.us[ch] - IDLE_US) > ACTIVE_DEADBAND:
                    self.active_s_total[ch] += dt
        self.last_checkpoint = now

    # ---- lifecycle ---------------------------------------------------------
    def start(self):
        self.stop_flag.clear()
        self.last_checkpoint = time.monotonic()
        self.clock_thread = threading.Thread(target=self._clock_loop, daemon=True)
        self.tel_thread = threading.Thread(target=self._tel_loop, daemon=True)
        self.clock_thread.start()
        self.tel_thread.start()
        self._boot_done()

    def _boot_done(self):
        self.boot_time = time.monotonic()
        self.usb_q.put("EVT BOOT")
        time.sleep(0.2)                 # simulated Wi-Fi join
        self.usb_q.put("EVT IP 127.0.0.1")
        self.net_up.set()

    def stop(self):
        self.stop_flag.set()

    def reboot(self):
        threading.Thread(target=self._do_reboot, daemon=True).start()

    def _do_reboot(self):
        self.net_up.clear()
        with self.lock:
            if self.client is not None:   # power loss kills the TCP connection
                self.client.closed = True
                self.client = None
        self.stop_flag.set()
        time.sleep(0.3)  # simulated boot time
        with self.lock:
            self._load_counters()
            self.state = "STOPPED"
            self.us = [IDLE_US] * CH
            self.load_buf = None
            self.profile = None
            self.profile_len = 0
            self.cycle_run = 0
            self.target = 0
            self.frame_idx = 0
            self.tel_enabled = False
            self.last_checkpoint = time.monotonic()
        self.stop_flag.clear()
        self.clock_thread = threading.Thread(target=self._clock_loop, daemon=True)
        self.tel_thread = threading.Thread(target=self._tel_loop, daemon=True)
        self.clock_thread.start()
        self.tel_thread.start()
        self._boot_done()

    # ---- background threads -------------------------------------------------
    def _clock_loop(self):
        # Uses absolute wake-up times (next_tick += period) rather than a
        # plain sleep(period) per frame: on Windows, time.sleep() routinely
        # overshoots by several ms (coarse OS timer granularity), and a naive
        # per-frame sleep would let that error accumulate into real drift
        # over a whole cycle. Scheduling against a fixed absolute clock keeps
        # the long-run average period accurate even if one frame is late.
        next_tick = None
        while not self.stop_flag.is_set():
            with self.lock:
                running = self.state == "RUNNING"
                rate = self.profile_rate or 50
            if not running:
                next_tick = None  # resync cleanly on the next START/RESUME
                time.sleep(0.02)
                continue
            period = 1.0 / rate
            if next_tick is None:
                next_tick = time.monotonic() + period
            sleep_for = next_tick - time.monotonic()
            if sleep_for > 0:
                time.sleep(sleep_for)
            next_tick += period
            if self.stop_flag.is_set():
                return
            with self.lock:
                self._checkpoint()
                if self.state != "RUNNING":
                    continue
                self.frame_idx += 1
                if self.frame_idx >= self.profile_len:
                    self.frame_idx = 0
                    self.cycle_run += 1
                    self.cycles_total += 1
                    self._emit("EVT CYCLE %d" % self.cycle_run)
                    if self.target and self.cycle_run >= self.target:
                        self.state = "STOPPED"
                        self.us = [IDLE_US] * CH
                        self.frame_idx = 0
                        self._checkpoint()
                        self._emit("EVT DONE")
                        self.save_counters()
                        continue
                self.us = list(self.profile[self.frame_idx])
                if time.monotonic() - self.last_save >= 60:
                    self.save_counters()

    def _tel_loop(self):
        next_time = time.monotonic() + 0.5
        while not self.stop_flag.is_set():
            now = time.monotonic()
            if now < next_time:
                time.sleep(min(0.05, next_time - now))
                continue
            next_time += 0.5
            with self.lock:
                if self.tel_enabled:
                    self._checkpoint()
                    line = "TEL state=%s cycle=%d frame=%d us=%s" % (
                        self.state, self.cycle_run, self.frame_idx,
                        ",".join(str(v) for v in self.us))
                    self._emit(line)

    # ---- connections (PROTOCOL.md section 1, Wi-Fi rules) ---------------------
    def _emit(self, line):
        """TEL/EVT lines go to USB serial AND the connected TCP client."""
        self.usb_q.put(line)
        c = self.client
        if c is not None and not c.closed:
            c.q.put(line)

    def connect_client(self, c):
        with self.lock:
            if self.client is not None:
                self.client.closed = True   # rule 3: new client takes over
            self.client = c
            self.tel_enabled = False        # rule 6: TEL off for a new client

    def disconnect_client(self, c):
        with self.lock:
            if self.client is c:
                self.client = None          # rule 4: keep running regardless

    # ---- command handling ---------------------------------------------------
    def handle(self, raw, src):
        """One command line from `src` (USB or a TCP client); the reply goes
        back to src.q only."""
        if not raw.strip():
            return  # empty line: ignored, no reply (PROTOCOL.md section 1)
        if len(raw) > 128:
            src.q.put(_err("ARGS", "line too long"))
            return
        with self.lock:
            self._checkpoint()
            reply = self._dispatch(raw)
        src.q.put(reply)

    def _abort_upload(self):
        self.load_buf = None
        self.load_rate = None
        self.load_expected = None
        self.load_next = 0

    def _dispatch(self, line):
        tokens = line.split()
        if not tokens:
            return _err("UNKNOWN")
        cmd, args = tokens[0], tokens[1:]

        if cmd == "PING":
            return "OK PONG"

        if cmd == "INFO":
            return "OK INFO proto=1 team=%s ch=%d maxframes=%d up=%d" % (
                TEAM, CH, MAXFRAMES, int(time.monotonic() - self.boot_time))

        if cmd == "SET":
            if self.state != "STOPPED":
                return _err("STATE", "not stopped")
            if len(args) != 2:
                return _err("ARGS")
            ch, us = _to_int(args[0]), _to_int(args[1])
            if ch is None or us is None:
                return _err("ARGS")
            if not (0 <= ch < CH):
                return _err("RANGE", "channel %d does not exist" % ch)
            if not (500 <= us <= 2500):
                return _err("RANGE", "us out of range")
            self.us[ch] = us
            return "OK"

        if cmd == "LOAD":
            if self.state != "STOPPED":
                return _err("STATE", "not stopped")
            if len(args) != 2:
                return _err("ARGS")
            rate, frames = _to_int(args[0]), _to_int(args[1])
            if rate is None or frames is None:
                return _err("ARGS")
            if not (10 <= rate <= 100):
                return _err("RANGE", "rate out of range")
            if frames > MAXFRAMES:
                return _err("FULL")
            if frames < 1:
                return _err("RANGE", "frames out of range")
            self.load_rate = rate
            self.load_expected = frames
            self.load_buf = [None] * frames
            self.load_next = 0
            self.profile = None  # LOAD discards any old (committed) profile
            self.profile_len = 0
            return "OK"

        if cmd == "F":
            if self.load_buf is None:
                return _err("STATE", "no LOAD in progress")
            if len(args) != 1 + CH:
                self._abort_upload()
                return _err("ARGS")
            i = _to_int(args[0])
            if i is None or i != self.load_next:
                self._abort_upload()
                return _err("ARGS", "frame out of order")
            vals = [_to_int(v) for v in args[1:]]
            if any(v is None for v in vals):
                self._abort_upload()
                return _err("ARGS")
            if any(v < 500 or v > 2500 for v in vals):
                self._abort_upload()
                return _err("RANGE")
            self.load_buf[i] = vals
            self.load_next += 1
            return "OK"

        if cmd == "COMMIT":
            if self.load_buf is None:
                return _err("STATE", "no LOAD in progress")
            if self.load_next != self.load_expected:
                return _err("STATE", "not all frames received")
            total = 0
            for frame in self.load_buf:
                total += sum(frame)
            self.profile = self.load_buf
            self.profile_len = self.load_expected
            self.profile_rate = self.load_rate
            self._abort_upload()
            return "OK SUM=%d" % (total % 65536)

        if cmd == "START":
            if self.state != "STOPPED":
                return _err("STATE", "not stopped")
            if not self.profile:
                return _err("NOPROFILE")
            if len(args) > 1:
                return _err("ARGS")
            target = 0
            if len(args) == 1:
                target = _to_int(args[0])
                if target is None:
                    return _err("ARGS")
                if target < 0:
                    return _err("RANGE")
            self.target = target
            self.cycle_run = 0
            self.frame_idx = 0
            self.us = list(self.profile[0])
            self.state = "RUNNING"
            self.last_checkpoint = time.monotonic()
            return "OK"

        if cmd == "PAUSE":
            if self.state != "RUNNING":
                return _err("STATE", "not running")
            self.state = "PAUSED"
            self.save_counters()
            return "OK"

        if cmd == "RESUME":
            if self.state != "PAUSED":
                return _err("STATE", "not paused")
            self.state = "RUNNING"
            self.last_checkpoint = time.monotonic()
            return "OK"

        if cmd == "STOP":
            self.state = "STOPPED"
            self.us = [IDLE_US] * CH
            self.frame_idx = 0
            self.save_counters()
            return "OK"

        if cmd == "STATUS":
            return "OK STATUS state=%s cycle=%d target=%d frame=%d frames=%d us=%s" % (
                self.state, self.cycle_run, self.target, self.frame_idx,
                self.profile_len, ",".join(str(v) for v in self.us))

        if cmd == "COUNTERS":
            return "OK COUNTERS cycles=%d run_s=%d active_s=%s" % (
                round(self.cycles_total), round(self.run_s_total),
                ",".join(str(round(x)) for x in self.active_s_total))

        if cmd == "CLEAR":
            if self.state != "STOPPED":
                return _err("STATE", "not stopped")
            self.cycles_total = 0.0
            self.run_s_total = 0.0
            self.active_s_total = [0.0] * CH
            self.save_counters()
            return "OK"

        if cmd == "TEL":
            if len(args) != 1 or args[0] not in ("0", "1"):
                return _err("ARGS")
            self.tel_enabled = (args[0] == "1")
            return "OK"

        if cmd == "TIME":
            if len(args) != 1 or _to_int(args[0]) is None:
                return _err("ARGS")
            return "OK"  # bonus level only, not automatically scored

        return _err("UNKNOWN")


# ==========================================================================
# ReplyReader: sits on top of a Transport, gives command/reply semantics plus
# a side-channel for the async TEL/EVT lines a level's timing checks need.
# Per PROTOCOL.md: any line not starting with OK/ERR/TEL/EVT is ignored.
# ==========================================================================

class ReplyReader:
    def __init__(self, transport):
        self.t = transport
        self.pending = []  # [(timestamp, line)] TEL/EVT seen while waiting for a reply
        self.owed = []     # expiry times of replies still due for timed-out commands

    def send(self, cmd, timeout=REPLY_TIMEOUT):
        self.t.write_line(cmd)
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self.owed.append(time.monotonic() + LATE_REPLY_WINDOW)
                return None
            line = self.t.read_line(remaining)
            if line is None:
                if not getattr(self.t, "closed", False):
                    self.owed.append(time.monotonic() + LATE_REPLY_WINDOW)
                return None
            if line.startswith("OK") or line.startswith("ERR"):
                now = time.monotonic()
                self.owed = [t for t in self.owed if t > now]
                if self.owed:
                    # A late reply to an earlier, timed-out command: skip it,
                    # or every later check would be one reply out of step.
                    self.owed.pop(0)
                    continue
                return line
            if line.startswith("TEL") or line.startswith("EVT"):
                self.pending.append((time.monotonic(), line))
            # else: debug print, ignored per protocol

    def collect(self, duration, stop_on=None):
        """Listen for `duration` seconds (or until a line for which
        stop_on(line) is True), returning [(timestamp, line), ...] of
        TEL/EVT/OK/ERR lines seen (including any stashed by send())."""
        out = list(self.pending)
        self.pending.clear()
        deadline = time.monotonic() + duration
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return out
            line = self.t.read_line(remaining)
            if line is None:
                continue
            if line.startswith(("OK", "ERR", "TEL", "EVT")):
                out.append((time.monotonic(), line))
                if stop_on and stop_on(line):
                    return out

    def wait_for(self, prefix, timeout):
        """Wait up to `timeout` s for a line starting with `prefix`."""
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            line = self.t.read_line(remaining)
            if line is None:
                continue
            if line.startswith(prefix):
                return True


def parse_kv(line):
    """'OK STATUS state=RUNNING cycle=3 ...' -> {'state':'RUNNING','cycle':'3',...}"""
    d = {}
    for tok in line.split()[2:]:
        if "=" in tok:
            k, v = tok.split("=", 1)
            d[k] = v
    return d


# ==========================================================================
# Test profile generator (shared by Levels 3/4/5)
# ==========================================================================

def build_profile(n_ch, frames=50):
    """A smooth multi-channel profile. If n_ch >= 2, the LAST channel is held
    at idle (1500) throughout, so Level 5 can check that active_s only counts
    channels that are actually away from idle."""
    profile = []
    for i in range(frames):
        row = []
        for ch in range(n_ch):
            if n_ch >= 2 and ch == n_ch - 1:
                row.append(IDLE_US)
            else:
                row.append(int(round(IDLE_US + 400 * math.sin(2 * math.pi * i / frames + ch))))
        profile.append(row)
    return profile


# ==========================================================================
# Check bookkeeping
# ==========================================================================

class Check:
    def __init__(self, name, points, max_points, ok, reason=""):
        self.name = name
        self.points = points
        self.max_points = max_points
        self.ok = ok
        self.reason = reason

    def line(self):
        tag = "PASS" if self.ok else "FAIL"
        r = (" - " + self.reason) if self.reason else ""
        return "  [%s] %-42s %2d/%2d%s" % (tag, self.name, self.points, self.max_points, r)


def ck_fail(name, max_points, reason=""):
    return Check(name, 0, max_points, False, reason)


def ck_skip(name, max_points, reason="skipped (--no-reset)"):
    return Check(name, 0, max_points, False, reason)


def is_err(reply, code):
    return reply is not None and reply.split()[:2] == ["ERR", code]


def ck(name, max_points, ok, reason=""):
    return Check(name, max_points if ok else 0, max_points, ok, "" if ok else reason)


def need_wifi(b, name, max_points):
    """Returns a zero-score Check if this run has no Wi-Fi link, else None."""
    if not b.wifi:
        return ck_fail(name, max_points, "Wi-Fi not tested (no --host)")
    return None


def info_up(reply):
    try:
        return int(parse_kv(reply).get("up", ""))
    except (TypeError, ValueError):
        return None


def reboot_and_rejoin(b, within=20.0):
    """Power-cycle the board and wait for it to come back.
    Returns (booted, rejoined_in_s_or_None, info_reply). `booted` is True
    if EVT BOOT was seen on USB (None if there is no USB to watch)."""
    b.reboot()
    t0 = time.monotonic()
    booted = None
    if b.u is not None:
        booted = b.u.wait_for("EVT BOOT", 8.0)
    if not b.wifi:
        reply = b.r.send("INFO")
        return booted, None, reply
    if b.u is not None:
        # Wait for the board to announce its IP before connecting. Knocking
        # on the address while the board is still offline makes Windows mark
        # it unreachable for a while, and every retry then times out.
        b.u.wait_for("EVT IP", max(0.0, within - (time.monotonic() - t0)))
    else:
        time.sleep(3.0)  # give a hand-power-cycled board a head start
    reply = b.reconnect(within - (time.monotonic() - t0))
    took = time.monotonic() - t0 if reply else None
    return booted, took, reply


# ==========================================================================
# Level runners. Each takes (bench, info_dict, args) and returns [Check].
# Each level re-establishes its own prerequisites (STOP, fresh upload, etc.)
# so it can be run standalone via --level N.
# ==========================================================================

def level1(b, info, args):
    """Hello, over USB (falls back to the control link if no --serial)."""
    checks = []
    r = b.u if b.u is not None else b.r

    reply = r.send("PING")
    checks.append(ck("PING -> OK PONG", 1, reply == "OK PONG", "got %r" % reply))

    reply = r.send("INFO")
    ok, reason = False, "got %r" % reply
    if reply and reply.startswith("OK INFO"):
        kv = parse_kv(reply)
        try:
            ok = (kv.get("proto") == "1" and int(kv.get("ch", "0")) >= 1
                  and int(kv.get("maxframes", "0")) >= 500 and "team" in kv
                  and info_up(reply) is not None)
            reason = "malformed or missing fields (proto/team/ch/maxframes/up): %s" % kv
        except ValueError:
            reason = "non-numeric ch/maxframes: %s" % kv
    checks.append(ck("INFO well-formed", 1, ok, reason))

    reply = r.send("FROBNICATE")
    checks.append(ck("Unknown command -> ERR UNKNOWN", 1, is_err(reply, "UNKNOWN"), "got %r" % reply))

    if not b.can_reboot():
        checks.append(ck_skip("EVT BOOT after reset", 2))
    elif b.u is None:
        checks.append(ck_fail("EVT BOOT after reset", 2, "needs --serial to see USB output"))
        reboot_and_rejoin(b)
    else:
        booted, _, _ = reboot_and_rejoin(b)
        checks.append(ck("EVT BOOT after reset", 2, bool(booted), "no EVT BOOT within 8s"))
    b.r.send("STOP")
    return checks


def level2(b, info, args):
    """Wi-Fi link: EVT IP, TCP answers, client takeover, TEL off for new client."""
    checks = []

    # EVT IP on USB after a boot
    name = "EVT IP on USB after boot"
    if not b.wifi:
        checks.append(ck_fail(name, 3, "Wi-Fi not tested (no --host)"))
    elif b.u is None:
        checks.append(ck_fail(name, 3, "needs --serial to see USB output"))
    elif not b.can_reboot():
        checks.append(ck_skip(name, 3))
    else:
        b.reboot()
        seen = b.u.wait_for("EVT IP", 20.0)
        b.reconnect(20.0)
        checks.append(ck(name, 3, seen, "no EVT IP within 20s of reset"))

    c = need_wifi(b, "TCP port 3333 answers PING/INFO", 2)
    if c:
        checks.append(c)
    else:
        p = b.r.send("PING")
        i = b.r.send("INFO")
        ok = p == "OK PONG" and i is not None and i.startswith("OK INFO")
        checks.append(ck("TCP port 3333 answers PING/INFO", 2, ok, "PING=%r INFO=%r" % (p, i)))

    c1 = need_wifi(b, "Second client takes over", 3)
    c2 = need_wifi(b, "TEL off for a new client", 2)
    if c1:
        checks += [c1, c2]
        return checks

    old = b.link
    b.r.send("TEL 1")  # old client asks for telemetry...
    try:
        b.connect()     # ...then a second client connects
    except OSError as e:
        checks.append(ck_fail("Second client takes over", 3, "second connect failed: %s" % e))
        checks.append(ck_fail("TEL off for a new client", 2, "second connect failed"))
        b.reconnect(5.0)
        return checks
    new_ok = b.r.send("PING") == "OK PONG"
    deadline = time.monotonic() + 2.0
    while not old.closed and time.monotonic() < deadline:
        old.read_line(0.1)  # drain; EOF sets .closed
    closed_by_board = old.closed
    old.close()
    checks.append(ck("Second client takes over", 3, new_ok and closed_by_board,
                     "new client PING ok=%s, old client closed by board=%s" % (new_ok, closed_by_board)))

    lines = b.r.collect(1.5)
    tel = [l for _, l in lines if l.startswith("TEL")]
    checks.append(ck("TEL off for a new client", 2, not tel, "new client got %d TEL lines" % len(tel)))
    b.r.send("TEL 0")
    return checks


def level3(b, info, args):
    """Manual PWM."""
    r = b.r
    checks = []
    n = info["ch"]
    r.send("STOP")

    reply = r.send("SET 0 1700")
    checks.append(ck("SET works", 1, reply == "OK", "got %r" % reply))

    reply = r.send("STATUS")
    ok = False
    if reply and reply.startswith("OK STATUS"):
        ok = parse_kv(reply).get("us", "").split(",")[0] == "1700"
    checks.append(ck("STATUS reflects new value", 1, ok, "got %r" % reply))

    reply = r.send("SET %d 1500" % n)  # channel n is out of range (0..n-1)
    checks.append(ck("Bad channel -> ERR RANGE", 1, is_err(reply, "RANGE"), "got %r" % reply))

    reply = r.send("SET 0 3000")
    checks.append(ck("Bad us -> ERR RANGE", 1, is_err(reply, "RANGE"), "got %r" % reply))

    reply = r.send("SET 0")
    checks.append(ck("Missing args -> ERR ARGS", 1, is_err(reply, "ARGS"), "got %r" % reply))

    r.send("SET 0 1500")
    return checks


def _upload(r, n, profile, rate=50):
    """LOAD/F/COMMIT a profile. Returns the SUM=<s> reply or None on failure."""
    if r.send("LOAD %d %d" % (rate, len(profile))) != "OK":
        return None
    for i, row in enumerate(profile):
        line = "F %d %s" % (i, " ".join(str(v) for v in row))
        if r.send(line) != "OK":
            return None
    return r.send("COMMIT")


def level4(b, info, args):
    """Profile upload."""
    r = b.r
    checks = []
    n = info["ch"]
    r.send("STOP")
    profile = build_profile(n, frames=20)

    reply = _upload(r, n, profile)
    ok = reply is not None and reply.startswith("OK SUM=")
    checks.append(ck("LOAD/F/COMMIT round-trip", 2, ok, "got %r" % reply))

    ok2, reason = False, "round-trip failed, can't check SUM"
    if ok:
        expected = sum(v for row in profile for v in row) % 65536
        try:
            got = int(reply.split("SUM=")[1])
        except ValueError:
            got = None
        ok2 = got == expected
        reason = "expected SUM=%d got %s" % (expected, got)
    checks.append(ck("SUM correct", 2, ok2, reason))

    idle = " ".join(str(IDLE_US) for _ in range(n))
    r.send("STOP")
    r.send("LOAD 50 5")
    r.send("F 0 %s" % idle)
    reply = r.send("F 2 %s" % idle)  # skip frame 1
    checks.append(ck("Out-of-order frame -> ERR ARGS", 2, is_err(reply, "ARGS"), "got %r" % reply))

    r.send("STOP")
    reply = r.send("LOAD 50 %d" % (info["maxframes"] + 1))
    checks.append(ck("Too many frames -> ERR FULL", 2, is_err(reply, "FULL"), "got %r" % reply))

    r.send("STOP")
    r.send("LOAD 50 5")
    r.send("F 0 %s" % idle)
    reply = r.send("COMMIT")  # only 1 of 5 frames sent
    checks.append(ck("Early COMMIT -> ERR STATE", 2, is_err(reply, "STATE"), "got %r" % reply))

    r.send("STOP")
    return checks


def cycle_period_check(name, points, cycle_ts, expected):
    """Average period from the first to the last EVT CYCLE, +-2%.
    Averaging over several cycles cancels out Wi-Fi delivery jitter."""
    if len(cycle_ts) < 3:
        return ck_fail(name, points, "only %d EVT CYCLE lines seen" % len(cycle_ts))
    avg = (cycle_ts[-1] - cycle_ts[0]) / (len(cycle_ts) - 1)
    err_pct = abs(avg - expected) / expected * 100
    return ck(name, points, err_pct <= 2.0,
              "avg period %.3fs vs expected %.3fs (%.1f%% off)" % (avg, expected, err_pct))


def level5(b, info, args):
    """Player."""
    r = b.r
    checks = []
    n = info["ch"]
    r.send("STOP")
    profile = build_profile(n, frames=50)  # rate 50, 50 frames -> 1.0s/cycle
    up = _upload(r, n, profile, rate=50)
    if up is None or not up.startswith("OK SUM="):
        checks.append(ck_fail("Profile upload for Level 5", 20,
                              "could not upload test profile, aborting level"))
        return checks

    bad = [is_err(r.send("PAUSE"), "STATE"), is_err(r.send("RESUME"), "STATE")]
    trans = [r.send("START") == "OK"]  # forever
    bad.append(is_err(r.send("SET 0 1600"), "STATE"))
    bad.append(is_err(r.send("START"), "STATE"))
    trans.append(r.send("PAUSE") == "OK")
    trans.append(r.send("RESUME") == "OK")
    trans.append(r.send("STOP") == "OK")
    checks.append(ck("State machine transitions", 5, all(trans), "sequence=%s" % trans))
    checks.append(ck("ERR STATE on invalid transitions", 4, all(bad), "sequence=%s" % bad))

    r.send("TEL 1")
    target = 6
    started = r.send("START %d" % target)
    if started != "OK":
        for name, pts in (("EVT CYCLE count/order", 3), ("EVT DONE + final STATUS", 2),
                          ("Cycle period within +-2%", 4), ("TEL interval ~500ms", 2)):
            checks.append(ck_fail(name, pts, "START failed: %r" % started))
        r.send("TEL 0")
        r.send("STOP")
        return checks

    events = r.collect(target * 1.0 + 3.0, stop_on=lambda l: l == "EVT DONE")
    r.send("TEL 0")
    cycle_ts = [ts for ts, l in events if l.startswith("EVT CYCLE")]
    cycle_ns = [l.split()[-1] for ts, l in events if l.startswith("EVT CYCLE")]
    done_seen = any(l == "EVT DONE" for ts, l in events)
    tel_ts = [ts for ts, l in events if l.startswith("TEL")]

    ok = cycle_ns == [str(i) for i in range(1, target + 1)]
    checks.append(ck("EVT CYCLE count/order", 3, ok, "got cycle numbers %s" % cycle_ns))

    status = r.send("STATUS")
    kv = parse_kv(status) if status else {}
    ok = done_seen and kv.get("state") == "STOPPED" and kv.get("cycle") == str(target)
    checks.append(ck("EVT DONE + final STATUS", 2, ok, "EVT DONE=%s STATUS=%r" % (done_seen, status)))

    checks.append(cycle_period_check("Cycle period within +-2%", 4, cycle_ts, 1.0))

    ok, reason = False, "fewer than 2 TEL lines seen"
    if len(tel_ts) >= 2:
        deltas = [tel_ts[i + 1] - tel_ts[i] for i in range(len(tel_ts) - 1)]
        # 500ms +-100ms per spec, plus slack for Wi-Fi delivery jitter
        bad_deltas = [d for d in deltas if not (0.25 <= d <= 0.80)]
        ok = len(bad_deltas) <= 1  # tolerate one outlier
        reason = "TEL deltas %s" % [round(d, 3) for d in deltas]
    checks.append(ck("TEL interval ~500ms", 2, ok, reason))

    r.send("STOP")
    return checks


def level6(b, info, args):
    """Counters survive power loss, board rejoins Wi-Fi."""
    r = b.r
    checks = []
    n = info["ch"]
    r.send("STOP")

    reply = r.send("CLEAR")
    reply2 = r.send("COUNTERS") if reply == "OK" else None
    kv = parse_kv(reply2) if reply2 else {}
    ok = (reply == "OK" and kv.get("cycles") == "0" and kv.get("run_s") == "0"
          and all(x == "0" for x in kv.get("active_s", "").split(",")))
    checks.append(ck("CLEAR works", 3, ok, "CLEAR=%r COUNTERS=%r" % (reply, reply2)))

    profile = build_profile(n, frames=50)  # 1.0s/cycle, last channel held at idle
    up = _upload(r, n, profile, rate=50)
    if up is None or not up.startswith("OK SUM="):
        for name, pts in (("COUNTERS grows while running", 3), ("active_s selectivity", 3),
                          ("Reboot: STOPPED, counters kept", 4), ("Back on Wi-Fi within 20s", 2)):
            checks.append(ck_fail(name, pts, "upload failed"))
        return checks

    r.send("START")  # forever
    time.sleep(5.0)
    reply = r.send("COUNTERS")
    kv_before = parse_kv(reply) if reply else {}
    ok = False
    try:
        ok = int(kv_before.get("cycles", "-1")) >= 2 and int(kv_before.get("run_s", "-1")) >= 3
    except ValueError:
        pass
    checks.append(ck("COUNTERS grows while running", 3, ok, "COUNTERS=%r" % reply))

    ok, reason = False, "COUNTERS malformed: %r" % reply
    try:
        act = [int(x) for x in kv_before.get("active_s", "").split(",")]
        if n >= 2 and len(act) == n:
            ok = act[-1] == 0 and all(act[i] > 0 for i in range(n - 1))
            reason = "active_s=%s (last channel held at idle)" % act
        else:
            ok = len(act) == n and all(a >= 0 for a in act)
            reason = "active_s=%s" % act
    except ValueError:
        pass
    checks.append(ck("active_s selectivity", 3, ok, reason))

    r.send("PAUSE")  # forces a save, per PROTOCOL.md section 7
    kv_pre = parse_kv(r.send("COUNTERS") or "")
    up_before = info_up(r.send("INFO"))

    if not b.can_reboot():
        checks.append(ck_skip("Reboot: STOPPED, counters kept", 4))
        checks.append(ck_skip("Back on Wi-Fi within 20s", 2))
        b.r.send("STOP")
        return checks

    booted, took, info_reply = reboot_and_rejoin(b, within=20.0)
    if b.wifi:
        checks.append(ck("Back on Wi-Fi within 20s", 2, took is not None,
                         "no TCP connection + INFO reply within 20s of reset"))
    else:
        checks.append(ck_fail("Back on Wi-Fi within 20s", 2, "Wi-Fi not tested (no --host)"))

    r = b.r
    ok, reason = False, "board did not come back"
    if info_reply:
        up_after = info_up(info_reply)
        status = r.send("STATUS")
        kv_s = parse_kv(status) if status else {}
        kv_after = parse_kv(r.send("COUNTERS") or "")
        try:
            rebooted = booted is True or (up_after is not None and up_before is not None
                                          and up_after < up_before)
            us_ok = kv_s.get("state") == "STOPPED" and \
                all(v == str(IDLE_US) for v in kv_s.get("us", "").split(","))
            cnt_ok = (int(kv_after.get("cycles", -1)) >= int(kv_pre.get("cycles", 0)) and
                      int(kv_after.get("run_s", -1)) >= int(kv_pre.get("run_s", 0)))
            act_b = [int(x) for x in kv_pre.get("active_s", "0").split(",")]
            act_a = [int(x) for x in kv_after.get("active_s", "0").split(",")]
            act_ok = len(act_b) == len(act_a) and all(a >= x for a, x in zip(act_a, act_b))
            ok = rebooted and us_ok and cnt_ok and act_ok
            reason = ("rebooted=%s STATUS=%r COUNTERS before=%r after=%r"
                      % (rebooted, status, kv_pre, kv_after))
        except (ValueError, TypeError):
            reason = "malformed STATUS/COUNTERS after reboot"
    checks.append(ck("Reboot: STOPPED, counters kept", 4, ok, reason))

    b.r.send("STOP")
    return checks


def level7(b, info, args):
    """Resilience: timing under load, link loss, junk input."""
    checks = []
    n = info["ch"]
    r = b.r
    r.send("STOP")
    profile = build_profile(n, frames=50)  # 1.0s/cycle
    up = _upload(r, n, profile, rate=50)
    if up is None or not up.startswith("OK SUM="):
        checks.append(ck_fail("Profile upload for Level 7", 15, "upload failed"))
    else:
        # (a) cycle period while the tool floods the board with commands
        target = 6
        r.send("START %d" % target)
        t_end = time.monotonic() + target * 1.0 + 3.0
        sent = 0
        while time.monotonic() < t_end:
            r.send("STATUS")
            sent += 1
            if any(l == "EVT DONE" for _, l in r.pending):
                break
        events = r.collect(0.2)
        cycle_ts = [ts for ts, l in events if l.startswith("EVT CYCLE")]
        c = cycle_period_check("Cycle period +-2% under command flood",
                               6, cycle_ts, 1.0)
        checks.append(c)

        # (b) the client vanishes mid-run
        c1 = need_wifi(b, "Keeps playing while client is gone", 6)
        c2 = need_wifi(b, "Counters keep counting while client is gone", 3)
        if c1:
            checks += [c1, c2]
        else:
            r.send("STOP")
            r.send("START")  # forever
            time.sleep(1.5)
            kv0 = parse_kv(r.send("STATUS") or "")
            cn0 = parse_kv(r.send("COUNTERS") or "")
            b.drop_link()
            time.sleep(6.0)
            info_reply = b.reconnect(10.0)
            r = b.r
            kv1 = parse_kv(r.send("STATUS") or "") if info_reply else {}
            cn1 = parse_kv(r.send("COUNTERS") or "") if info_reply else {}
            try:
                dc = int(kv1.get("cycle", -99)) - int(kv0.get("cycle", 0))
                ok = kv1.get("state") == "RUNNING" and 5 <= dc <= 8
                reason = "state=%s, cycles advanced by %d while gone (expected ~6)" % (kv1.get("state"), dc)
            except ValueError:
                ok, reason = False, "malformed STATUS"
            checks.append(ck("Keeps playing while client is gone", 6, ok, reason))
            try:
                dr = int(cn1.get("run_s", -99)) - int(cn0.get("run_s", 0))
                ok = dr >= 5
                reason = "run_s advanced by %d (expected >= 5)" % dr
            except ValueError:
                ok, reason = False, "malformed COUNTERS"
            checks.append(ck("Counters keep counting while client is gone", 3, ok, reason))
        r.send("STOP")

    # (c) junk input
    def still_alive():
        # A late ERR for the junk line may still be in flight, so skip
        # any OK/ERR lines until OK PONG shows up (or time runs out).
        r.t.write_line("PING")
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline:
            line = r.t.read_line(deadline - time.monotonic())
            if line == "OK PONG":
                return True
        return False

    r.send("ZQX 1 2 3", timeout=0.3)
    checks.append(ck("Survives garbage line", 1, still_alive(), "PING failed after garbage line"))
    r.send("A" * 200, timeout=0.3)
    checks.append(ck("Survives 200-char line", 1, still_alive(), "PING failed after long line"))
    r.send("", timeout=0.3)
    checks.append(ck("Survives empty line", 1, still_alive(), "PING failed after empty line"))

    n_burst = 50
    for _ in range(n_burst):
        r.t.write_line("PING")
    got = 0
    deadline = time.monotonic() + 5.0
    while got < n_burst and time.monotonic() < deadline:
        line = r.t.read_line(deadline - time.monotonic())
        if line == "OK PONG":
            got += 1
        elif line is None:
            break
    checks.append(ck("Burst of %d commands" % n_burst, 2, got == n_burst,
                     "got %d/%d replies" % (got, n_burst)))
    return checks


LEVELS = [
    (1, "Hello (USB)", 5, level1),
    (2, "Wi-Fi link", 10, level2),
    (3, "Manual PWM", 5, level3),
    (4, "Profile upload", 10, level4),
    (5, "Player", 20, level5),
    (6, "Counters / power loss", 15, level6),
    (7, "Resilience", 20, level7),
]


def cmd_test(args):
    try:
        b = Bench(args)
    except OSError as e:
        print("FATAL: could not connect: %s" % e)
        return 1
    try:
        reply = b.r.send("INFO")
        if reply is None or not reply.startswith("OK INFO"):
            print("FATAL: board did not answer INFO. Is it flashed, on Wi-Fi, and is the IP/port right?")
            return 1
        info_kv = parse_kv(reply)
        info = {"ch": int(info_kv.get("ch", "1")), "maxframes": int(info_kv.get("maxframes", "500"))}
        print("Board: %s" % reply)
        print("Link:  %s%s" % ("Wi-Fi" if b.wifi else "USB serial only (Wi-Fi checks score 0)",
                               ", USB attached" if b.usb is not None and b.wifi else ""))
        print()

        levels_to_run = LEVELS if args.level is None else [lv for lv in LEVELS if lv[0] == args.level]
        if not levels_to_run:
            print("No such level: %d (valid: 1-7)" % args.level)
            return 1

        results = {"board_info": info_kv, "levels": []}
        grand_points = 0
        grand_max = 0
        for num, name, max_pts, fn in levels_to_run:
            print("Level %d: %s (%d pts)" % (num, name, max_pts))
            checks = fn(b, info, args)
            for c in checks:
                print(c.line())
            pts = sum(c.points for c in checks)
            mx = sum(c.max_points for c in checks)
            print("  Level %d total: %d/%d" % (num, pts, mx))
            print()
            grand_points += pts
            grand_max += mx
            results["levels"].append({
                "level": num, "name": name, "points": pts, "max_points": mx,
                "checks": [{"name": c.name, "points": c.points, "max_points": c.max_points,
                            "pass": c.ok, "reason": c.reason} for c in checks],
            })

        print("=" * 60)
        print("TOTAL: %d / %d" % (grand_points, grand_max))
        results["total_points"] = grand_points
        results["total_max"] = grand_max

        if args.json:
            with open(args.json, "w") as f:
                json.dump(results, f, indent=2)
            print("Wrote %s" % args.json)
        return 0
    finally:
        b.close()


# ==========================================================================
# upload
# ==========================================================================

def cmd_upload(args):
    with open(args.file, newline="") as f:
        rdr = csv.reader(f)
        header = next(rdr)
        if not header or header[0] != "t_ms" or not all(h.startswith("ch") for h in header[1:]):
            print("ERROR: CSV header must be 't_ms,ch0,ch1,...' got %r" % header)
            return 1
        n_ch = len(header) - 1
        if n_ch < 1:
            print("ERROR: CSV has no channel columns")
            return 1
        rows = []
        for lineno, row in enumerate(rdr, start=2):
            if not row:
                continue
            try:
                vals = [int(float(x)) for x in row[1:1 + n_ch]]
            except ValueError:
                print("ERROR: row %d has a non-numeric value: %r" % (lineno, row))
                return 1
            bad = [v for v in vals if v < 500 or v > 2500]
            if bad:
                print("ERROR: row %d has out-of-range us value(s) %s (must be 500..2500)"
                      % (lineno, bad))
                return 1
            rows.append(vals)
    if not rows:
        print("ERROR: CSV has no data rows")
        return 1

    b = Bench(args)
    r = b.r
    try:
        reply = r.send("STOP")
        print("STOP -> %s" % reply)
        reply = r.send("LOAD %d %d" % (args.rate, len(rows)))
        print("LOAD %d %d -> %s" % (args.rate, len(rows), reply))
        if reply != "OK":
            print("Upload aborted.")
            return 1
        for i, vals in enumerate(rows):
            line = "F %d %s" % (i, " ".join(str(v) for v in vals))
            reply = r.send(line)
            if reply != "OK":
                print("Frame %d failed: %s -> %s" % (i, line, reply))
                return 1
        reply = r.send("COMMIT")
        print("COMMIT -> %s" % reply)
        if not reply or not reply.startswith("OK SUM="):
            print("COMMIT failed.")
            return 1
        expected = sum(v for row in rows for v in row) % 65536
        got = int(reply.split("SUM=")[1])
        if got != expected:
            print("WARNING: SUM mismatch: board said %d, expected %d" % (got, expected))
            return 1
        print("Uploaded %d frames x %d channels at %d Hz. SUM verified." % (len(rows), n_ch, args.rate))
        return 0
    finally:
        b.close()


# ==========================================================================
# term (interactive)
# ==========================================================================

def cmd_term(args):
    b = Bench(args)
    t = b.link
    print("Connected (%s). Type commands (PING, INFO, ...). Ctrl-C to quit."
          % ("Wi-Fi" if b.wifi else "USB serial"))
    stop_flag = threading.Event()

    def reader_thread():
        while not stop_flag.is_set():
            line = t.read_line(0.2)
            if line is not None:
                print(line)

    th = threading.Thread(target=reader_thread, daemon=True)
    th.start()
    try:
        while True:
            try:
                cmd = input("> ")
            except EOFError:
                break
            if cmd.strip().lower() in ("quit", "exit"):
                break
            t.write_line(cmd)
    except KeyboardInterrupt:
        pass
    finally:
        stop_flag.set()
        b.close()
    return 0


# ==========================================================================
# soak
# ==========================================================================

def cmd_soak(args):
    b = Bench(args)
    r = b.r
    try:
        reply = r.send("INFO")
        if not reply or not reply.startswith("OK INFO"):
            print("FATAL: board did not answer INFO.")
            return 1
        kv = parse_kv(reply)
        n = int(kv.get("ch", "1"))
        print("Board: %s" % reply)

        r.send("STOP")
        profile = build_profile(n, frames=50)
        reply = _upload(r, n, profile, rate=50)
        if not reply or not reply.startswith("OK SUM="):
            print("FATAL: profile upload failed: %r" % reply)
            return 1
        r.send("TEL 1")
        started = r.send("START")  # forever
        if started != "OK":
            print("FATAL: START failed: %r" % started)
            return 1

        print("Soaking for %.1f minutes. Polling STATUS/COUNTERS every 5s." % args.minutes)
        start_time = time.time()
        end_time = start_time + args.minutes * 60
        errors = 0
        timeouts = 0
        polls = 0
        last_cycle = 0

        while time.time() < end_time:
            r.collect(5.0)  # drain TEL/EVT for 5s (also keeps buffers from filling)
            status = r.send("STATUS")
            counters = r.send("COUNTERS")
            polls += 1
            if status is None or counters is None:
                timeouts += 1
                continue
            if not status.startswith("OK") or not counters.startswith("OK"):
                errors += 1
                continue
            skv = parse_kv(status)
            try:
                cycle = int(skv.get("cycle", last_cycle))
            except ValueError:
                cycle = last_cycle
            if cycle < last_cycle:
                errors += 1
            last_cycle = cycle
            print("  t=%5ds state=%s cycle=%s run_s=%s"
                  % (int(time.time() - start_time), skv.get("state"),
                     skv.get("cycle"), parse_kv(counters).get("run_s")))

        r.send("STOP")
        print()
        print("Soak summary: %d polls, %d errors, %d timeouts, final cycle=%d"
              % (polls, errors, timeouts, last_cycle))
        return 0 if (errors == 0 and timeouts == 0) else 1
    finally:
        b.close()



# ==========================================================================
# serve-sim: the simulated bench as a real TCP server on this PC
# ==========================================================================

class _SockClient:
    """Bridges one TCP socket to the SimDevice (acts like a SimLinkTransport)."""

    def __init__(self, sock):
        self.sock = sock
        self.q = queue.Queue()
        self.closed = False

    def pump_out(self):
        while not self.closed:
            try:
                line = self.q.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                self.sock.sendall((line + "\n").encode("ascii"))
            except OSError:
                break
        try:
            self.sock.close()
        except OSError:
            pass

    def read_lines(self):
        buf = b""
        while not self.closed:
            try:
                self.sock.settimeout(0.2)
                chunk = self.sock.recv(4096)
            except OSError as e:
                if "timed out" in str(e):
                    continue
                break
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                yield line.replace(b"\r", b"").decode("ascii", errors="replace")
        self.closed = True


def cmd_serve_sim(args):
    import socket
    dev = SimDevice()
    dev.start()

    def serve(port, on_client):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", port))
        srv.listen(4)
        while True:
            sock, _ = srv.accept()
            threading.Thread(target=on_client, args=(sock,), daemon=True).start()

    def bench_client(sock):
        # Like the real board: no connections while "rebooting".
        if not dev.net_up.wait(timeout=0.1):
            sock.close()
            return
        c = _SockClient(sock)
        dev.connect_client(c)
        threading.Thread(target=c.pump_out, daemon=True).start()
        for line in c.read_lines():
            dev.handle(line, c)
        c.closed = True
        dev.disconnect_client(c)

    usb = {"c": None}

    def usb_forwarder():  # what the board prints on "USB" -> the virtual USB client
        while True:
            line = dev.usb_q.get()
            c = usb["c"]
            if c is not None and not c.closed:
                c.q.put(line)

    def usb_client(sock):
        # Test-only virtual USB port: board output, commands, and "!RESET".
        c = _SockClient(sock)
        usb["c"] = c
        threading.Thread(target=c.pump_out, daemon=True).start()
        for line in c.read_lines():
            if line == "!RESET":
                dev.reboot()
            else:
                dev.handle(line, c)

    threading.Thread(target=usb_forwarder, daemon=True).start()
    threading.Thread(target=serve, args=(args.usb_port, usb_client), daemon=True).start()
    print("Simulated bench running. Connect your controller to 127.0.0.1:%d" % args.listen)
    print("Leave this window open. Press Ctrl-C to stop.")
    try:
        serve(args.listen, bench_client)
    except KeyboardInterrupt:
        pass
    return 0

# ==========================================================================
# makecsv
# ==========================================================================

def cmd_makecsv(args):
    n_ch = args.channels
    rate = args.rate
    n_frames = int(args.seconds * rate)
    header = ["t_ms"] + ["ch%d" % i for i in range(n_ch)]
    rows = []
    for i in range(n_frames):
        t_ms = int(round(i * 1000.0 / rate))
        row = [t_ms]
        for ch in range(n_ch):
            # a gentle banking-manoeuvre-like sweep, phase-offset per channel
            phase = 2 * math.pi * i / n_frames + ch * (math.pi / max(1, n_ch))
            us = IDLE_US + int(round(700 * math.sin(phase)))
            us = max(500, min(2500, us))
            row.append(us)
        rows.append(row)
    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print("Wrote %s: %d frames, %d channels, %d Hz (%.1fs)" % (args.out, n_frames, n_ch, rate, args.seconds))
    return 0


# ==========================================================================
# argparse wiring
# ==========================================================================

def main():
    p = argparse.ArgumentParser(prog="wdr_tool.py", description="WDR protocol PC tool.")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_target(sp):
        sp.add_argument("--host", default=None, help="Board IP on Wi-Fi (TCP port 3333)")
        sp.add_argument("--tcp-port", dest="tcp_port", type=int, default=3333)
        sp.add_argument("--serial", default=None,
                        help="Board USB serial port (COM5, /dev/ttyUSB0) for EVT BOOT/EVT IP and resets")
        sp.add_argument("--port", default=None,
                        help="'sim' for the built-in simulated bench; a COM port = --serial")
        sp.add_argument("--no-reset", dest="no_reset", action="store_true",
                        help="Never reboot the board (reboot checks score 0, noted)")

    pt = sub.add_parser("test", help="Run the SCORING.md conformance scorer.")
    add_target(pt)
    pt.add_argument("--level", type=int, default=None, help="Run only this level (1-7)")
    pt.add_argument("--json", default=None, help="Write full results to this JSON file")
    pt.set_defaults(func=cmd_test)

    pu = sub.add_parser("upload", help="Upload a CSV flight profile.")
    pu.add_argument("file", help="CSV file with header t_ms,ch0,ch1,...")
    add_target(pu)
    pu.add_argument("--rate", type=int, default=50, help="Playback rate, frames/sec (10-100)")
    pu.set_defaults(func=cmd_upload)

    ptm = sub.add_parser("term", help="Interactive terminal.")
    add_target(ptm)
    ptm.set_defaults(func=cmd_term)

    ps = sub.add_parser("soak", help="Long-running endurance check.")
    add_target(ps)
    ps.add_argument("--minutes", type=float, required=True)
    ps.set_defaults(func=cmd_soak)

    pss = sub.add_parser("serve-sim", help="Run the simulated bench as a TCP server on this PC.")
    pss.add_argument("--listen", type=int, default=3333, help="Bench TCP port (default 3333)")
    pss.add_argument("--usb-port", dest="usb_port", type=int, default=3334,
                     help="Test-only virtual USB port (default 3334); use --serial tcp://127.0.0.1:3334")
    pss.set_defaults(func=cmd_serve_sim)

    pm = sub.add_parser("makecsv", help="Generate a sample flight CSV.")
    pm.add_argument("out", help="Output CSV path")
    pm.add_argument("--channels", type=int, default=4)
    pm.add_argument("--rate", type=int, default=50)
    pm.add_argument("--seconds", type=float, default=4.0)
    pm.set_defaults(func=cmd_makecsv)

    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
