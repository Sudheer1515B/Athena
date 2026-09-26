import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'bench_api.dart';
import 'theme.dart';

/// Recent pulse widths reported by STATUS, sampled by the local backend.
class LiveTrace extends StatelessWidget {
  const LiveTrace({super.key, required this.samples, this.physical = false});

  final List<TraceSample> samples;
  final bool physical;

  @override
  Widget build(BuildContext context) {
    if (samples.isEmpty) {
      return SizedBox(
        height: 230,
        child: Center(
          child: Text(
            physical
                ? 'No fresh receiver measurements.'
                : 'No live bench command samples.',
          ),
        ),
      );
    }
    final channelCount = samples.last.pulseUs.length;
    final first = samples.first.sampledAt?.toLocal();
    final last = samples.last.sampledAt?.toLocal();
    String clock(DateTime? value) => value == null
        ? '—'
        : '${value.hour.toString().padLeft(2, '0')}:'
              '${value.minute.toString().padLeft(2, '0')}:'
              '${value.second.toString().padLeft(2, '0')}';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          height: 190,
          width: double.infinity,
          child: CustomPaint(painter: _TracePainter(samples)),
        ),
        const SizedBox(height: 5),
        Row(
          children: [
            Text(clock(first), style: const TextStyle(fontSize: 11)),
            const Spacer(),
            Text(clock(last), style: const TextStyle(fontSize: 11)),
          ],
        ),
        const SizedBox(height: 9),
        Wrap(
          spacing: 14,
          runSpacing: 4,
          children: [
            for (var index = 0; index < channelCount; index++)
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    width: 12,
                    height: 3,
                    color: Palette.series[index % Palette.series.length],
                  ),
                  const SizedBox(width: 5),
                  Text('OUT$index', style: const TextStyle(fontSize: 11)),
                ],
              ),
          ],
        ),
        const SizedBox(height: 6),
        Text(
          physical
              ? 'Independent receiver HIGH widths · missing pulses create gaps, not zero values'
              : 'Sampled command pulses from STATUS · not physical feedback',
          style: const TextStyle(color: Palette.muted, fontSize: 11),
        ),
      ],
    );
  }
}

class _TracePainter extends CustomPainter {
  const _TracePainter(this.samples);

  final List<TraceSample> samples;

  @override
  void paint(Canvas canvas, Size size) {
    const left = 37.0;
    const top = 8.0;
    const bottom = 7.0;
    final plotWidth = math.max(1.0, size.width - left - 5);
    final plotHeight = math.max(1.0, size.height - top - bottom);
    double y(int value) =>
        top + (2500 - value.clamp(500, 2500)) / 2000 * plotHeight;
    final grid = Paint()
      ..color = Palette.line
      ..strokeWidth = 1;
    for (final mark in [500, 1500, 2500]) {
      final row = y(mark);
      canvas.drawLine(Offset(left, row), Offset(size.width, row), grid);
      final label = TextPainter(
        text: TextSpan(
          text: '$mark',
          style: const TextStyle(fontSize: 10, color: Palette.muted),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      label.paint(canvas, Offset(0, row - label.height / 2));
    }
    final start = samples.first.sampledAt;
    final end = samples.last.sampledAt;
    final duration = start == null || end == null
        ? 0
        : end.difference(start).inMilliseconds;
    double x(int index) {
      if (duration > 0 && samples[index].sampledAt != null) {
        final elapsed = samples[index].sampledAt!
            .difference(start!)
            .inMilliseconds;
        return left + elapsed.clamp(0, duration) / duration * plotWidth;
      }
      return left + index / math.max(1, samples.length - 1) * plotWidth;
    }

    final channels = samples.last.pulseUs.length;
    for (var channel = 0; channel < channels; channel++) {
      final paint = Paint()
        ..color = Palette.series[channel % Palette.series.length]
        ..strokeWidth = 2
        ..style = PaintingStyle.stroke;
      final path = Path();
      var hasPoint = false;
      for (var index = 0; index < samples.length; index++) {
        if (channel >= samples[index].pulseUs.length ||
            samples[index].pulseUs[channel] <= 0) {
          hasPoint = false;
          continue;
        }
        final point = Offset(x(index), y(samples[index].pulseUs[channel]));
        if (!hasPoint) {
          path.moveTo(point.dx, point.dy);
          hasPoint = true;
        } else {
          path.lineTo(point.dx, point.dy);
        }
      }
      canvas.drawPath(path, paint);
      if (hasPoint && samples.last.pulseUs[channel] > 0) {
        final lastPoint = Offset(
          x(samples.length - 1),
          y(samples.last.pulseUs[channel]),
        );
        canvas.drawCircle(lastPoint, 3, Paint()..color = paint.color);
      }
    }
  }

  @override
  bool shouldRepaint(covariant _TracePainter oldDelegate) => true;
}
