import 'package:athena/motor_monitoring.dart';
import 'package:athena/bench_api.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Map<String, dynamic> status({bool fresh = true}) => {
  'command_fresh': fresh,
  'bench_age_s': .2,
  'current_all_low_reported': true,
  'receiver_fresh': false,
  'channels': [
    for (var i = 0; i < 4; i++) {'bench_reported_us': 1000},
  ],
  'replay': {
    'active': true,
    'phase': 'RUNNING',
    'total_frames': 150,
    'acknowledged_frames': 60,
    'frames_per_pass': 50,
    'requested_passes': 3,
    'rate_hz': 50,
    'elapsed_s': 1.2,
    'max_lateness_s': .001,
    'started_at': '2026-09-26T07:00:00Z',
  },
};

void main() {
  Future<void> mount(
    WidgetTester tester,
    Map<String, dynamic> data, {
    bool backendLive = true,
    Future<void> Function()? cancel,
  }) async {
    tester.view.physicalSize = const Size(1200, 1600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: MotorMonitoring(
              data: data,
              samples: [
                TraceSample(
                  sampledAt: DateTime.utc(2026),
                  pulseUs: const [1000, 1000, 1000, 1000],
                  frame: 0,
                  cycle: 0,
                  state: 'STOPPED',
                ),
              ],
              backendLive: backendLive,
              busy: false,
              onCancel: cancel ?? () async {},
              onIdle: () async {},
            ),
          ),
        ),
      ),
    );
  }

  testWidgets('no receiver does not imply motors are measured or running', (
    tester,
  ) async {
    var cancelled = false;
    await mount(tester, status(), cancel: () async => cancelled = true);
    expect(find.text('Bench: 1000 µs'), findsNWidgets(4));
    expect(find.textContaining('Measured PWM:'), findsNothing);
    expect(find.text('Motor RPM: not measured'), findsNWidgets(4));
    expect(
      find.text('60/150 frames acknowledged · pass 2/3 · profile 50 Hz'),
      findsOneWidget,
    );
    await tester.tap(find.text('Cancel motor replay & request 1000 µs'));
    expect(cancelled, isTrue);
    expect(tester.takeException(), isNull);
  });

  testWidgets('backend outage hides cached commands and graph', (tester) async {
    await mount(tester, status(), backendLive: false);
    expect(find.text('Bench: UNKNOWN'), findsNWidgets(4));
    expect(find.text('Current 1000 µs output state: UNKNOWN'), findsOneWidget);
    expect(find.text('No live bench command samples.'), findsOneWidget);
    expect(
      find.text('Bench currently reports all four outputs at 1000 µs'),
      findsNothing,
    );
    expect(
      find.text('Last known, stale: motor action RUNNING'),
      findsOneWidget,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('Wi-Fi staleness hides widths but preserves cancel request', (
    tester,
  ) async {
    await mount(tester, status(fresh: false));
    expect(find.text('Bench: UNKNOWN'), findsNWidgets(4));
    final button = tester.widget<OutlinedButton>(
      find.widgetWithText(
        OutlinedButton,
        'Cancel motor replay & request 1000 µs',
      ),
    );
    expect(button.onPressed, isNotNull);
    expect(tester.takeException(), isNull);
  });
}
