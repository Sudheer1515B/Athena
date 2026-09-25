import 'package:athena/app_state.dart';
import 'package:athena/main.dart';
import 'package:athena/bench_api.dart';
import 'package:athena/live_trace.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets(
    'empty dashboard shows disconnected state and disabled controls',
    (tester) async {
      tester.view.physicalSize = const Size(1440, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final state = AppState();
      addTearDown(state.dispose);
      await tester.pumpWidget(MyApp(state: state));
      expect(find.text('BENCH DISCONNECTED'), findsOneWidget);
      expect(
        find.text('Connect a bench to view its reported channels.'),
        findsOneWidget,
      );
      final start = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, '▶ Start 1 cycle'),
      );
      expect(start.onPressed, isNull);
      expect(find.text('127'), findsNothing);
    },
  );

  testWidgets('profile navigation uses the supplied four-stage structure', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1440, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final state = AppState();
    addTearDown(state.dispose);
    await tester.pumpWidget(MyApp(state: state));
    await tester.tap(find.text('Profile'));
    await tester.pump();
    expect(find.text('1 · SOURCE LOG'), findsOneWidget);
    expect(find.text('4 · PUSH TO BENCH'), findsOneWidget);
  });

  testWidgets('sampled pulse trace renders four reported channels', (
    tester,
  ) async {
    final first = DateTime.utc(2026, 9, 26, 0, 0, 0);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SizedBox(
            width: 700,
            child: LiveTrace(
              samples: [
                TraceSample(
                  sampledAt: first,
                  pulseUs: const [1050, 1100, 1200, 1300],
                  frame: 0,
                  cycle: 0,
                  state: 'RUNNING',
                ),
                TraceSample(
                  sampledAt: first.add(const Duration(seconds: 1)),
                  pulseUs: const [1500, 1600, 1700, 1800],
                  frame: 50,
                  cycle: 0,
                  state: 'RUNNING',
                ),
              ],
            ),
          ),
        ),
      ),
    );
    expect(find.text('OUT0'), findsOneWidget);
    expect(find.text('OUT3'), findsOneWidget);
    expect(find.textContaining('not physical feedback'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
