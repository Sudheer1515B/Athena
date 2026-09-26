"""Describe available motor-command evidence without inventing physical telemetry."""


def motor_monitoring(live, motor, receiver):
    connection = live.get("connection") or {}
    observation = live.get("observation") or {}
    fresh = connection.get("state") == "CONNECTED" and observation.get("fresh") is True
    raw = (live.get("bench_state") or {}).get("us", "")
    try:
        widths = [int(value) for value in raw.split(",")]
        if len(widths) != 4 or any(not 500 <= value <= 2500 for value in widths):
            widths = None
    except (ValueError, AttributeError):
        widths = None
    if not fresh:
        widths = None
    physical = bool(receiver and receiver.get("fresh"))
    measurements = receiver.get("channels") if physical else None
    if not isinstance(measurements, list) or len(measurements) != 4:
        measurements = None
        physical = False
    channels = []
    for index, gpio in enumerate((25, 26, 27, 33)):
        width = widths[index] if widths else None
        measured = measurements[index] if measurements else None
        channels.append({
            "channel": index, "bench_gpio": gpio,
            "bench_reported_us": width,
            "command_state": "UNKNOWN" if width is None else
                "OUTSIDE_CONFIRMED_RANGE" if not 1000 <= width <= 2000 else
                "LOW_COMMAND" if width == 1000 else "ABOVE_LOW_COMMAND",
            "physical_pwm_state": "UNKNOWN" if measured is None else
                "PWM_PRESENT" if measured.get("signal") else "NO_SIGNAL",
            "measured_us": measured.get("width_us") if measured and measured.get("signal") else None,
            "measured_period_us": measured.get("period_us") if measured and measured.get("signal") else None,
            "motor_rpm": None, "motor_current_a": None, "motor_temperature_c": None,
        })
    low = all(width == 1000 for width in widths) if widths else None
    return {
        "command_fresh": widths is not None,
        "command_source": "BENCH_STATUS",
        "bench_last_seen_at": observation.get("last_seen_at"),
        "bench_age_s": observation.get("age_s"),
        "bench_connection": connection.get("state", "UNKNOWN"),
        "bench_state": (live.get("bench_state") or {}).get("state") if widths else None,
        "current_all_low_reported": low,
        "receiver_fresh": physical,
        "receiver_configured": bool(receiver and receiver.get("configured")),
        "channels": channels,
        "replay": motor,
        "physical_motor_telemetry_available": False,
        "scope": "Command/readback monitoring. PWM receiver feedback, when connected, does not establish motor motion, RPM, current or temperature.",
    }
