import 'package:athena/app_state.dart';
import 'package:athena/main.dart';
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
        find.widgetWithText(FilledButton, '▶ Start'),
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
}
