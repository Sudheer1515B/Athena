import 'package:athena/receiver_feedback.dart';
import 'package:athena/app_state.dart';
import 'package:athena/bench_api.dart';
import 'package:athena/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class RecoveryApi extends BenchApi {
  int restarts = 0;
  @override
  Future<BenchSnapshot> restartRecovery(String id, int cycles) async {
    restarts++;
    return BenchSnapshot.fromJson({
      'connection': {'state': 'CONNECTED'},
    });
  }
}

void main() {
  final data = {
    'configured': true,
    'fresh': true,
    'channels': [
      for (var i = 0; i < 4; i++)
        {
          'signal': i != 1,
          'width_us': i == 1 ? null : 1500,
          'period_us': i == 1 ? null : 20000,
        },
    ],
    'trace': [
      {
        'sampled_at': '2026-09-26T00:00:00Z',
        'us': [1500, null, 1500, 1500],
      },
    ],
  };
  testWidgets(
    'missing physical pulse is explicit and not a normal command trace',
    (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(body: ReceiverFeedback(data: data, backendLive: true)),
        ),
      );
      expect(find.text('OUT1 NO SIGNAL'), findsOneWidget);
      expect(find.text('OUT0 1500 µs / 20000 µs'), findsOneWidget);
      expect(find.textContaining('missing pulses create gaps'), findsOneWidget);
    },
  );
  testWidgets('backend outage removes old measured graph and widths', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: ReceiverFeedback(data: data, backendLive: false)),
      ),
    );
    expect(find.text('OUT0 UNKNOWN'), findsOneWidget);
    expect(find.text('OUT0 1500 µs / 20000 µs'), findsNothing);
    expect(find.text('No fresh receiver measurements.'), findsOneWidget);
  });

  testWidgets('all missing signals remove the measured graph', (tester) async {
    final missing = Map<String, dynamic>.from(data);
    missing['channels'] = [
      for (var i = 0; i < 4; i++)
        {'signal': false, 'width_us': null, 'period_us': null},
    ];
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ReceiverFeedback(data: missing, backendLive: true),
        ),
      ),
    );
    expect(
      find.textContaining('NO PWM SIGNAL · check bench power'),
      findsOneWidget,
    );
    expect(
      find.textContaining('Independent receiver HIGH widths'),
      findsNothing,
    );
  });
  testWidgets('power recovery waits for review and explicit approval', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1440, 1800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final api = RecoveryApi();
    final state = AppState(api: api);
    addTearDown(state.dispose);
    state.snapshot = BenchSnapshot.fromJson({
      'connection': {'state': 'CONNECTED'},
      'observation': {'fresh': true},
      'recovery': {
        'id': 'proposal',
        'remaining_cycles': 2,
        'last_observed_frame': 42,
        'message': 'The interrupted cycle restarts.',
      },
    });
    await tester.pumpWidget(MyApp(state: state));
    expect(api.restarts, 0);
    await tester.tap(find.text('Review restart…'));
    await tester.pumpAndSettle();
    expect(find.text('Approve re-upload and restart?'), findsOneWidget);
    expect(api.restarts, 0);
    await tester.tap(find.text('Approve restart'));
    await tester.pumpAndSettle();
    expect(api.restarts, 1);
    expect(find.text('Review restart…'), findsNothing);
  });
}
