import 'package:flutter/material.dart';

import 'theme.dart';

class MotorRecovery extends StatelessWidget {
  const MotorRecovery({
    super.key,
    required this.recovery,
    required this.ready,
    required this.busy,
    required this.onResume,
  });
  final Map<String, dynamic> recovery;
  final bool ready, busy;
  final Future<void> Function(String) onResume;
  @override
  Widget build(BuildContext context) {
    final cursor = recovery['acknowledged_frames'] as int;
    final count = recovery['total_frames'] as int;
    final framesPerPass = recovery['frames_per_pass'] as int;
    final partial =
        recovery['in_flight_frame'] != null ||
        recovery['partial_frame_uncertain'] == true;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(border: Border.all(color: Palette.critical)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text(
            'Motor replay interrupted · approval required',
            style: TextStyle(
              color: Palette.critical,
              fontWeight: FontWeight.w700,
            ),
          ),
          Text(
            'Saved $cursor/$count complete frame acknowledgements. ${cursor < count ? 'Next: pass ${cursor ~/ framesPerPass + 1}, frame ${cursor % framesPerPass + 1}.' : 'All frames were acknowledged; low-output finalization remains.'}',
          ),
          Text(
            partial
                ? 'The interrupted frame may have reached some outputs. Resume repeats that entire frame. Physical motor position is unknown.'
                : 'Resume begins at the next saved command frame. The last frame’s physical dwell/motor motion through the outage is unknown.',
          ),
          const Text(
            'Power-loss stop depends on ESC failsafe. Bench boot still outputs 1500 µs; isolate motor power through boot, then request/read back 1000 µs on all four outputs.',
            style: TextStyle(color: Palette.critical, fontSize: 12),
          ),
          if (!ready)
            const Text(
              'Waiting for a fresh connection to the stopped bench and all-four 1000 µs readback.',
              style: TextStyle(color: Palette.muted),
            ),
          const SizedBox(height: 8),
          OutlinedButton(
            onPressed: busy || !ready
                ? null
                : () async {
                    var hardwareConfirmed = false;
                    final approved = await showDialog<bool>(
                      context: context,
                      builder: (dialogContext) => StatefulBuilder(
                        builder: (context, setDialogState) => AlertDialog(
                          title: const Text('Resume saved motor commands?'),
                          content: SingleChildScrollView(
                            child: Column(
                              mainAxisSize: MainAxisSize.min,
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  'Resume profile ${recovery['profile_id']} at saved absolute frame $cursor (zero based), preserving the remaining passes and approved ceiling. The outage is excluded from the profile clock.',
                                ),
                                const SizedBox(height: 10),
                                const Text(
                                  'This resumes commands, not a verified physical motor position. Partial-frame delivery and interrupted dwell may repeat. This firmware has no electrical power interlock.',
                                ),
                                CheckboxListTile(
                                  contentPadding: EdgeInsets.zero,
                                  value: hardwareConfirmed,
                                  onChanged: (value) => setDialogState(
                                    () => hardwareConfirmed = value ?? false,
                                  ),
                                  title: const Text(
                                    'I verified missing-PWM ESC stopping and protection from 1500 µs boot output, the same bench/motor wiring, props removed, secured drone, attended power cutoff, and accept the delivery uncertainty.',
                                  ),
                                ),
                              ],
                            ),
                          ),
                          actions: [
                            TextButton(
                              onPressed: () =>
                                  Navigator.pop(dialogContext, false),
                              child: const Text('Keep stopped'),
                            ),
                            FilledButton(
                              onPressed: hardwareConfirmed
                                  ? () => Navigator.pop(dialogContext, true)
                                  : null,
                              child: const Text('Approve motor resume'),
                            ),
                          ],
                        ),
                      ),
                    );
                    if (approved == true) {
                      await onResume(recovery['run_id'].toString());
                    }
                  },
            child: const Text('Review saved motor resume…'),
          ),
        ],
      ),
    );
  }
}
