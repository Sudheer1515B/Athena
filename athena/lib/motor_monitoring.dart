import 'package:flutter/material.dart';

import 'bench_api.dart';
import 'live_trace.dart';
import 'theme.dart';

class MotorMonitoring extends StatelessWidget {
  const MotorMonitoring({
    super.key,
    required this.data,
    required this.samples,
    required this.backendLive,
    required this.busy,
    required this.onCancel,
    required this.onIdle,
  });
  final Map<String, dynamic>? data;
  final List<TraceSample> samples;
  final bool backendLive, busy;
  final Future<void> Function() onCancel, onIdle;

  @override
  Widget build(BuildContext context) {
    final fresh = backendLive && data?['command_fresh'] == true;
    final replay = data?['replay'] as Map?;
    final active = replay?['active'] == true;
    final channels = data?['channels'] as List? ?? [];
    final low = fresh ? (data?['current_all_low_reported']) : null;
    final total = (replay?['total_frames'] as num?)?.toInt() ?? 0;
    final sent = (replay?['acknowledged_frames'] as num?)?.toInt() ?? 0;
    final framesPerPass = (replay?['frames_per_pass'] as num?)?.toInt() ?? 0;
    final passes = (replay?['requested_passes'] as num?)?.toInt() ?? 0;
    final pass = framesPerPass > 0 && passes > 0
        ? (sent == 0 ? 1 : (sent - 1) ~/ framesPerPass + 1).clamp(1, passes)
        : null;
    return BenchCard(
      title: 'Drone motor monitoring',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            fresh
                ? 'Live bench command readback · ${data?['bench_age_s'] ?? '?'} s old'
                : 'Command readback UNKNOWN · bench or backend is unavailable/stale',
            style: TextStyle(
              color: fresh ? Palette.secondary : Palette.critical,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            low == true
                ? 'Bench currently reports all four outputs at 1000 µs'
                : low == false
                ? 'One or more reported outputs are not at 1000 µs'
                : 'Current 1000 µs output state: UNKNOWN',
            style: TextStyle(
              color: low == true ? Palette.secondary : Palette.critical,
            ),
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 12,
            runSpacing: 12,
            children: [
              for (var index = 0; index < 4; index++)
                SizedBox(
                  width: 200,
                  child: Builder(
                    builder: (_) {
                      final channel = index < channels.length
                          ? channels[index] as Map
                          : const {};
                      final width = fresh ? channel['bench_reported_us'] : null;
                      final measured =
                          backendLive && data?['receiver_fresh'] == true;
                      final physical = !measured
                          ? 'UNKNOWN'
                          : channel['physical_pwm_state'] == 'NO_SIGNAL'
                          ? 'NO SIGNAL'
                          : '${channel['measured_us']} µs';
                      return Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          border: Border.all(color: Palette.line),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'OUT$index · GPIO${[25, 26, 27, 33][index]}',
                              style: const TextStyle(
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                            const SizedBox(height: 5),
                            Text(
                              'Bench: ${width == null ? 'UNKNOWN' : '$width µs'}',
                              style: TextStyle(
                                color: width == null
                                    ? Palette.critical
                                    : Palette.ink,
                              ),
                            ),
                            if (fresh &&
                                channel['command_state'] ==
                                    'OUTSIDE_CONFIRMED_RANGE')
                              const Text(
                                'Outside 1000–2000 µs',
                                style: TextStyle(
                                  color: Palette.critical,
                                  fontSize: 11,
                                ),
                              ),
                            Text(
                              'Measured PWM: $physical',
                              style: TextStyle(
                                color:
                                    physical == 'UNKNOWN' ||
                                        physical == 'NO SIGNAL'
                                    ? Palette.critical
                                    : Palette.secondary,
                                fontSize: 12,
                              ),
                            ),
                            const Text(
                              'Motor RPM: not measured',
                              style: TextStyle(
                                color: Palette.muted,
                                fontSize: 11,
                              ),
                            ),
                          ],
                        ),
                      );
                    },
                  ),
                ),
            ],
          ),
          const SizedBox(height: 12),
          LiveTrace(samples: fresh ? samples : const []),
          const Text(
            'The graph samples bench STATUS; it is not a measurement of electrical output or motor speed. Without a receiver, pulling an ESC signal wire cannot be detected here.',
            style: TextStyle(color: Palette.muted, fontSize: 11),
          ),
          const SizedBox(height: 12),
          if (replay != null) ...[
            Text(
              '${backendLive ? '' : 'Last known, stale: '}motor action ${replay['phase'] ?? 'UNKNOWN'}',
              style: const TextStyle(fontWeight: FontWeight.w700),
            ),
            if (total > 0) ...[
              const SizedBox(height: 6),
              LinearProgressIndicator(
                value: (sent / total).clamp(0, 1).toDouble(),
              ),
              const SizedBox(height: 6),
              Text(
                '$sent/$total frames acknowledged${pass == null ? '' : ' · pass $pass/$passes'} · profile ${replay['rate_hz'] ?? '?'} Hz',
              ),
            ],
            Text(
              '${replay['elapsed_s'] ?? '?'} s elapsed · maximum schedule lateness ${replay['max_lateness_s'] ?? '?'} s',
            ),
            if (replay['profile_id'] != null)
              Text(
                'Profile: ${replay['profile_id']}',
                style: const TextStyle(color: Palette.muted, fontSize: 11),
              ),
            if (replay['started_at'] != null)
              Text('Started: ${replay['started_at']}'),
            if (replay['ended_at'] != null)
              Text('Ended: ${replay['ended_at']}'),
            if (replay['last_low_readback_at'] != null)
              Text(
                'Last action low readback: ${replay['last_low_readback_at']} (historical)',
                style: const TextStyle(color: Palette.muted, fontSize: 11),
              ),
            if (replay['error'] != null)
              Text(
                replay['error'].toString(),
                style: const TextStyle(color: Palette.critical),
              ),
            if (replay['checkpoint_error'] != null)
              Text(
                'Recovery checkpoint write failed: ${replay['checkpoint_error']}. Saved progress may lag.',
                style: const TextStyle(color: Palette.critical),
              ),
            const SizedBox(height: 10),
          ],
          OutlinedButton(
            onPressed: !backendLive || busy || !active && !fresh
                ? null
                : active
                ? onCancel
                : onIdle,
            child: Text(
              active
                  ? 'Cancel motor replay & request 1000 µs'
                  : 'Request 1000 µs on all four outputs',
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            'SET replay progress is host accounting; it does not add native bench cycles/hours. Motor motion, RPM, current and temperature are unavailable without additional feedback.',
            style: TextStyle(color: Palette.muted, fontSize: 11),
          ),
        ],
      ),
    );
  }
}
