import 'package:flutter/material.dart';

import 'bench_api.dart';
import 'live_trace.dart';
import 'theme.dart';

class ReceiverFeedback extends StatelessWidget {
  const ReceiverFeedback({
    super.key,
    required this.data,
    required this.backendLive,
  });
  final Map<String, dynamic>? data;
  final bool backendLive;
  @override
  Widget build(BuildContext context) {
    final fresh = backendLive && data?['fresh'] == true;
    final channels = fresh ? (data?['channels'] as List?) : null;
    final anySignal =
        channels?.any((channel) => (channel as Map)['signal'] == true) ?? false;
    final samples = fresh
        ? (data?['trace'] as List? ?? []).map((raw) {
            final item = Map<String, dynamic>.from(raw as Map);
            item['us'] = (item['us'] as List)
                .map((value) => value ?? 0)
                .toList();
            return TraceSample.fromJson(item);
          }).toList()
        : <TraceSample>[];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          fresh
              ? 'Physical measurements · receiver connected'
              : data?['configured'] == true
              ? 'Receiver feedback unavailable or stale'
              : 'Connect the PWM receiver in Settings',
          style: TextStyle(color: fresh ? Palette.secondary : Palette.critical),
        ),
        const SizedBox(height: 10),
        Wrap(
          spacing: 14,
          runSpacing: 8,
          children: [
            for (var index = 0; index < 4; index++)
              Text(
                channels == null
                    ? 'OUT$index UNKNOWN'
                    : (channels[index] as Map)['signal'] != true
                    ? 'OUT$index NO SIGNAL'
                    : 'OUT$index ${(channels[index] as Map)['width_us']} µs / ${(channels[index] as Map)['period_us'] ?? '?'} µs',
                style: TextStyle(
                  color:
                      channels == null ||
                          (channels[index] as Map)['signal'] != true
                      ? Palette.critical
                      : Palette.ink,
                ),
              ),
          ],
        ),
        const SizedBox(height: 10),
        if (fresh && !anySignal)
          const SizedBox(
            height: 190,
            child: Center(
              child: Text(
                'NO PWM SIGNAL · check bench power, wiring and common ground',
                style: TextStyle(color: Palette.critical),
              ),
            ),
          )
        else
          LiveTrace(samples: samples, physical: true),
        const Text(
          'Signal loss is electrical evidence at the receiver input. It does not prove servo position, load or wear.',
          style: TextStyle(color: Palette.muted, fontSize: 11),
        ),
      ],
    );
  }
}
