import 'package:athena/motor_recovery.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  final recovery = <String, dynamic>{
    'run_id': 'run',
    'profile_id': 'profile',
    'acknowledged_frames': 60,
    'total_frames': 150,
    'frames_per_pass': 50,
    'in_flight_frame': 60,
    'partial_frame_uncertain': true,
  };
  testWidgets(
    'saved frame resume requires explicit hardware review and approval',
    (tester) async {
      tester.view.physicalSize = const Size(1200, 1600);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      var resumed = 0;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: MotorRecovery(
              recovery: recovery,
              ready: true,
              busy: false,
              onResume: (id) async {
                expect(id, 'run');
                resumed++;
              },
            ),
          ),
        ),
      );
      expect(resumed, 0);
      expect(find.textContaining('Next: pass 2, frame 11.'), findsOneWidget);
      await tester.tap(find.text('Review saved motor resume…'));
      await tester.pumpAndSettle();
      final approve = find.widgetWithText(FilledButton, 'Approve motor resume');
      expect(tester.widget<FilledButton>(approve).onPressed, isNull);
      expect(resumed, 0);
      await tester.tap(find.byType(CheckboxListTile));
      await tester.pump();
      await tester.tap(approve);
      await tester.pumpAndSettle();
      expect(resumed, 1);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('recovery cannot resume before connected all-low readback', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MotorRecovery(
            recovery: recovery,
            ready: false,
            busy: false,
            onResume: (_) async {},
          ),
        ),
      ),
    );
    expect(
      tester
          .widget<OutlinedButton>(
            find.widgetWithText(OutlinedButton, 'Review saved motor resume…'),
          )
          .onPressed,
      isNull,
    );
    expect(
      find.textContaining('Waiting for a fresh connection'),
      findsOneWidget,
    );
    expect(tester.takeException(), isNull);
  });
}
