import 'package:athena/motor_send.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Map<String, dynamic> motorProfile(int peak, {bool unmapped = false}) => {
  'id': 'motor-profile',
  'settings': {
    'mapping': [
      for (var i = 0; i < 4; i++)
        {'source': unmapped && i == 3 ? null : 'C${i + 1}'},
    ],
  },
  'summary': {
    'ranges': [
      for (var i = 0; i < 4; i++) {'min_us': 1000, 'max_us': peak},
    ],
  },
};

void main() {
  testWidgets(
    'requires reviewed limits and confirmation before motor commands',
    (tester) async {
      tester.view.physicalSize = const Size(1200, 1600);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      List<Object>? sent;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: MotorSend(
              profile: motorProfile(1200),
              progress: null,
              connected: true,
              busy: false,
              onRun: (id, count, max) async => sent = [id, count, max],
              onCancel: () async {},
              onIdle: () async {},
            ),
          ),
        ),
      );
      final send = find.widgetWithText(
        FilledButton,
        'Send extracted commands to motors',
      );
      expect(tester.widget<FilledButton>(send).onPressed, isNull);
      await tester.tap(find.byType(CheckboxListTile));
      await tester.pump();
      expect(tester.widget<FilledButton>(send).onPressed, isNull);
      await tester.enterText(find.byType(TextField).first, '1200');
      await tester.pump();
      expect(tester.widget<FilledButton>(send).onPressed, isNull);
      await tester.tap(find.byType(CheckboxListTile));
      await tester.pump();
      await tester.tap(send);
      expect(sent, ['motor-profile', 1, 1200]);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('active playback exposes cancel and unconfirmed low status', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1200, 1600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    var cancelled = false;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MotorSend(
            profile: motorProfile(1080),
            connected: false,
            busy: true,
            progress: {
              'active': true,
              'phase': 'RUNNING',
              'acknowledged_frames': 2,
              'total_frames': 50,
              'elapsed_s': 1,
            },
            onRun: (_, _, _) async {},
            onCancel: () async => cancelled = true,
            onIdle: () async {},
          ),
        ),
      ),
    );
    expect(find.text('1000 µs readback: not confirmed'), findsOneWidget);
    await tester.tap(find.text('Cancel & request 1000 µs'));
    expect(cancelled, isTrue);
    expect(tester.takeException(), isNull);
  });
}
