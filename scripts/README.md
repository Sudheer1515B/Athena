# Capturing an already committed WDR profile

`capture_existing_profile.py` reconstructs the **commanded pulse widths** of a profile already saved on a WDR bench. WDR v1 has no direct profile-readback command. The script samples `STATUS frame=... us=...` during finite `START 1` replays and repeats up to the requested limit until it has observed every frame index. It never sends `LOAD`, `F`, `COMMIT`, `CLEAR`, or firmware-upload commands. A replay does drive the four outputs and increments the bench's lifetime counters.

Before replay, disconnect Athena from that bench and verify the outputs have no servos or other loads attached (or that any attached load may safely move). The independent receiver ESP32 may stay wired and USB-powered; this script neither opens its serial port nor flashes either board. First run the read-only preflight:

```sh
PYTHONPATH=. .venv/bin/python -u scripts/capture_existing_profile.py \
  --host 10.178.45.105 --port 3333 \
  --expected-team WDR_REFERENCE --expected-frames 100
```

The command must report `state=STOPPED`, `frames=100`, `team=WDR_REFERENCE`, and four channels. To capture, add `--replay` and an unused output directory:

```sh
PYTHONPATH=. .venv/bin/python -u scripts/capture_existing_profile.py \
  --host 10.178.45.105 --port 3333 \
  --expected-team WDR_REFERENCE --expected-frames 100 \
  --max-runs 3 --output-dir captures/reference_100frame_YYYYMMDD --replay
```

The directory contains raw `STATUS` observations, a manifest with before/after bench counters and coverage, and `reconstructed_frames.csv` only if all indices were observed without conflicting values. If the observed frame timing supports an integer rate, `reconstructed_approx_TimeUS.csv` is also produced for Athena import. Its timing is inferred from frame-index observations; the original upload rate, source file, labels and original checksum cannot be read from the bench. The manifest's `reconstructed_sum16` is computed from captured widths and is **not** an original checksum read from the device.

On 26 September 2026, the real reference bench capture at [reference_100frame_20260926](../captures/reference_100frame_20260926) observed all 100 indices after three finite runs. Every frame reported `1100,1300,1700,1900` µs, with an inferred rate of approximately 50 Hz. Athena's compiler reproduced all 100 captured frames from the approximate TimeUS file. The profile was not overwritten, reflashed, or cleared; lifetime cycles increased from 21 to 24.
