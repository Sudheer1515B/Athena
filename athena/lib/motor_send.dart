import 'package:flutter/material.dart';

import 'theme.dart';

class MotorSend extends StatefulWidget {
  const MotorSend({
    super.key,
    required this.profile,
    required this.progress,
    required this.connected,
    required this.busy,
    required this.onRun,
    required this.onCancel,
    required this.onIdle,
  });
  final Map<String, dynamic>? profile;
  final Map<String, dynamic>? progress;
  final bool connected, busy;
  final Future<void> Function(String, int, int) onRun;
  final Future<void> Function() onCancel, onIdle;
  @override
  State<MotorSend> createState() => _MotorSendState();
}

class _MotorSendState extends State<MotorSend> {
  final ceiling = TextEditingController(text: '1100');
  final cycles = TextEditingController(text: '1');
  bool confirmed = false;
  @override
  void dispose() {
    ceiling.dispose();
    cycles.dispose();
    super.dispose();
  }

  @override
  void didUpdateWidget(covariant MotorSend oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.profile?['id'] != widget.profile?['id']) confirmed = false;
  }

  @override
  Widget build(BuildContext context) {
    final active = widget.progress?['active'] == true;
    final maxUs = int.tryParse(ceiling.text);
    final count = int.tryParse(cycles.text);
    final ranges =
        (widget.profile?['summary'] as Map?)?['ranges'] as List? ?? [];
    final mapping =
        (widget.profile?['settings'] as Map?)?['mapping'] as List? ?? [];
    final allMapped =
        mapping.length == 4 &&
        mapping.every((item) => (item as Map)['source'] != null);
    final fits =
        ranges.length == 4 &&
        maxUs != null &&
        maxUs >= 1000 &&
        maxUs <= 2000 &&
        ranges.every(
          (range) =>
              (range as Map)['min_us'] >= 1000 && range['max_us'] <= maxUs,
        );
    return BenchCard(
      title: 'Motor commands · 4 outputs',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text(
            'Send the compiled profile directly over Wi-Fi using SET. No native upload is needed. Completion/cancel requests 1000 µs on all four outputs.',
            style: TextStyle(fontSize: 12.5),
          ),
          const SizedBox(height: 8),
          const Text(
            'Keep the Mac and Wi-Fi connected. A lost link can leave the last throttle applied; cut motor power. Bench reset still outputs 1500 µs. Four SET commands are sequential, not simultaneous.',
            style: TextStyle(color: Palette.critical, fontSize: 12),
          ),
          const SizedBox(height: 10),
          for (var i = 0; i < ranges.length; i++)
            Text(
              'OUT$i${i < 4 ? ' · GPIO${[25, 26, 27, 33][i]}' : ''}: ${ranges[i]['min_us']}–${ranges[i]['max_us']} µs',
              style: const TextStyle(color: Palette.secondary),
            ),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: ceiling,
                  enabled: !active,
                  keyboardType: TextInputType.number,
                  onChanged: (_) => setState(() => confirmed = false),
                  decoration: const InputDecoration(
                    labelText: 'Allowed ceiling µs',
                    border: OutlineInputBorder(),
                    isDense: true,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              SizedBox(
                width: 100,
                child: TextField(
                  controller: cycles,
                  enabled: !active,
                  keyboardType: TextInputType.number,
                  onChanged: (_) => setState(() {}),
                  decoration: const InputDecoration(
                    labelText: 'Passes (1–100)',
                    border: OutlineInputBorder(),
                    isDense: true,
                  ),
                ),
              ),
            ],
          ),
          if (widget.profile != null && (!allMapped || !fits))
            const Padding(
              padding: EdgeInsets.only(top: 8),
              child: Text(
                'Map all four outputs and keep every profile pulse between 1000 µs and your chosen ceiling. No values will be clipped.',
                style: TextStyle(color: Palette.critical, fontSize: 12),
              ),
            ),
          Material(
            color: Colors.transparent,
            child: CheckboxListTile(
              contentPadding: EdgeInsets.zero,
              value: confirmed,
              onChanged: active
                  ? null
                  : (value) => setState(() => confirmed = value ?? false),
              title: const Text(
                'Props removed, drone secured, power cutoff attended; 1000 µs stops these motors. I have reviewed all four output mappings and the pulse range.',
                style: TextStyle(fontSize: 12),
              ),
            ),
          ),
          FilledButton(
            onPressed:
                active ||
                    widget.busy ||
                    !widget.connected ||
                    widget.profile == null ||
                    !allMapped ||
                    !fits ||
                    !confirmed ||
                    count == null ||
                    count < 1 ||
                    count > 100
                ? null
                : () => widget.onRun(
                    widget.profile!['id'].toString(),
                    count,
                    maxUs,
                  ),
            child: const Text('Send extracted commands to motors'),
          ),
          const SizedBox(height: 8),
          OutlinedButton(
            onPressed: widget.busy && !active || !widget.connected && !active
                ? null
                : active
                ? widget.onCancel
                : widget.onIdle,
            child: Text(
              active ? 'Cancel & request 1000 µs' : 'Set all four to 1000 µs',
            ),
          ),
          if (widget.progress != null) ...[
            const SizedBox(height: 10),
            Text(
              '${widget.progress!['phase']} · ${widget.progress!['acknowledged_frames']}/${widget.progress!['total_frames']} frames acknowledged · ${widget.progress!['elapsed_s']} s',
            ),
            Text(
              '1000 µs readback: ${widget.progress!['low_signal_confirmed'] == true ? 'confirmed by bench' : 'not confirmed'}',
            ),
            if (widget.progress!['error'] != null)
              Text(
                widget.progress!['error'].toString(),
                style: const TextStyle(color: Palette.critical),
              ),
          ],
          const SizedBox(height: 8),
          const Text(
            'Host timing is checked; replay aborts if it falls too far behind. SET playback does not increment native bench cycles or running hours. PWM commands do not prove motor motion.',
            style: TextStyle(color: Palette.muted, fontSize: 11),
          ),
        ],
      ),
    );
  }
}
