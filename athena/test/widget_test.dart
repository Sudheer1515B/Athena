import 'dart:async';
import 'dart:ui' show PointerDeviceKind;

import 'package:athena/app_state.dart';
import 'package:athena/main.dart';
import 'package:athena/bench_api.dart';
import 'package:athena/live_trace.dart';
import 'package:athena/theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class FakeHistoryApi extends BenchApi {
  @override
  Future<List<Map<String, dynamic>>> historySessions(
    String? fromDate,
    String? throughDate,
  ) async => [
    {
      'id': 'completed',
      'bench_label': 'SIM',
      'channel_count': 2,
      'started_at': '2026-09-26T00:00:00Z',
      'status': 'COMPLETED',
      'target_cycles': 1,
      'observation_count': 3,
      'has_link_gap': false,
      'delta': {
        'cycles': 1,
        'run_s': 7200,
        'active_s': [3600, 7200],
      },
    },
    {
      'id': 'uncertain',
      'bench_label': 'SIM',
      'channel_count': 2,
      'started_at': '2026-09-25T00:00:00Z',
      'status': 'UNCONFIRMED',
      'target_cycles': 2,
      'observation_count': 1,
      'has_link_gap': true,
      'delta': null,
    },
  ];

  @override
  Future<List<Map<String, dynamic>>> historyEvents(
    String? fromDate,
    String? throughDate,
  ) async => [];

  @override
  Future<Map<String, dynamic>> historySession(String id) async =>
      id == 'uncertain'
      ? {
          'id': id,
          'status': 'UNCONFIRMED',
          'started_at': '2026-09-25T00:00:00Z',
          'ended_at': null,
          'stop_cause': null,
          'identity_confidence': 'uncertain',
          'target_cycles': 2,
          'delta': null,
          'bench_label': 'SIM',
          'bench_mode': 'simulator',
          'bench_host': '127.0.0.1',
          'bench_id': 'bench-1',
          'bench_capabilities': null,
          'source_name': null,
          'profile_id': null,
          'profile_settings': null,
          'counter_observations': [
            {
              'observed_at': '2026-09-25T00:00:00Z',
              'cycles': 0,
              'run_s': 0,
              'uptime_s': 10,
              'active_s': [0, 0],
            },
          ],
          'events': [],
          'has_link_gap': true,
          'counter_epoch_changed': false,
        }
      : {
          'id': id,
          'status': 'COMPLETED',
          'started_at': '2026-09-26T00:00:00Z',
          'ended_at': '2026-09-26T02:00:00Z',
          'stop_cause': 'Cycle target reached',
          'identity_confidence': 'observed',
          'target_cycles': 1,
          'delta': {
            'cycles': 1,
            'run_s': 7200,
            'active_s': [3600, 7200],
          },
          'bench_label': 'SIM',
          'bench_mode': 'simulator',
          'bench_host': '127.0.0.1',
          'bench_id': 'bench-1',
          'bench_capabilities': {'proto': '1', 'ch': '2', 'maxframes': '8000'},
          'source_name': 'flight.csv',
          'source_sha256': 'source-hash',
          'profile_id': 'profile-1',
          'profile_sha256': 'profile-hash',
          'profile_sum16': 12345,
          'profile_frame_count': 100,
          'profile_rate_hz': 50,
          'profile_settings': {
            'start_us': 0,
            'end_us': 2000000,
            'mapping': [
              {
                'output': 0,
                'source': 'C1',
                'label': 'A',
                'min_us': 500,
                'max_us': 2500,
              },
              {
                'output': 1,
                'source': 'C2',
                'label': 'B',
                'min_us': 500,
                'max_us': 2500,
              },
            ],
          },
          'counter_observations': [
            {
              'observed_at': '2026-09-26T00:00:00Z',
              'cycles': 0,
              'run_s': 0,
              'uptime_s': 10,
              'active_s': [0, 0],
            },
            {
              'observed_at': '2026-09-26T02:00:00Z',
              'cycles': 1,
              'run_s': 7200,
              'uptime_s': 7210,
              'active_s': [3600, 7200],
            },
          ],
          'events': [],
          'has_link_gap': false,
          'counter_epoch_changed': false,
        };
}

class BlockingUploadApi extends BenchApi {
  final pending = Completer<BenchSnapshot>();
  int uploadCalls = 0;

  @override
  Future<BenchSnapshot> uploadProfile(String profileId) {
    uploadCalls++;
    return pending.future;
  }
}

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
    await tester.tap(find.text('PROFILE'));
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

  testWidgets(
    'history shows persisted hours, unknown deltas and filtered details',
    (tester) async {
      tester.view.physicalSize = const Size(1440, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final state = AppState(api: FakeHistoryApi());
      addTearDown(state.dispose);
      await tester.pumpWidget(MyApp(state: state));
      await tester.tap(find.text('HISTORY'));
      await tester.pumpAndSettle();
      expect(
        find.text('Observed active hours by channel'.toUpperCase()),
        findsOneWidget,
      );
      expect(find.text('1.0000 h'), findsOneWidget);
      expect(find.text('2.0000 h'), findsOneWidget);
      expect(
        find.textContaining('1 unknown session deltas excluded'),
        findsOneWidget,
      );
      expect(find.textContaining('UNCONFIRMED'), findsOneWidget);

      await tester.tap(find.textContaining('SIM ·').first);
      await tester.pumpAndSettle();
      expect(find.textContaining('Source file: flight.csv'), findsOneWidget);
      expect(
        find.textContaining('Profile SHA-256: profile-hash'),
        findsOneWidget,
      );
      expect(find.textContaining('Counter observations · 2'), findsOneWidget);
      expect(find.textContaining('OUT0 mapping:'), findsOneWidget);

      await tester.tap(find.text('All channels'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('OUT1').last);
      await tester.pumpAndSettle();
      expect(find.textContaining('OUT1 mapping:'), findsOneWidget);
      expect(find.textContaining('OUT0 mapping:'), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('history flags disconnected sessions without inventing results', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1440, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final state = AppState(api: FakeHistoryApi());
    addTearDown(state.dispose);
    await tester.pumpWidget(MyApp(state: state));
    await tester.tap(find.text('HISTORY'));
    await tester.pumpAndSettle();
    final uncertain = find.textContaining('UNCONFIRMED');
    await tester.ensureVisible(uncertain);
    await tester.tap(uncertain);
    await tester.pumpAndSettle();
    expect(find.textContaining('Uncertain coverage:'), findsOneWidget);
    expect(find.textContaining('Counter delta: Unknown'), findsOneWidget);
    expect(find.textContaining('Source file: Unknown'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('metric tile reveal rises on hover and retreats on exit', (
    tester,
  ) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: Center(
            child: SizedBox(
              width: 300,
              child: HoverMetricTile(
                label: 'Cycles completed',
                value: '12',
                detail: 'Lifetime bench total',
              ),
            ),
          ),
        ),
      ),
    );
    final clip = find.descendant(
      of: find.byType(HoverMetricTile),
      matching: find.byType(ClipRect),
    );
    double revealHeight() => tester
        .widget<ClipRect>(clip)
        .clipper!
        .getClip(const Size(300, 100))
        .height;
    expect(revealHeight(), 0);
    expect(
      tester
          .widget<ColoredBox>(
            find.descendant(
              of: find.byType(HoverMetricTile),
              matching: find.byType(ColoredBox),
            ),
          )
          .color,
      Palette.ink,
    );

    final mouse = await tester.createGesture(kind: PointerDeviceKind.mouse);
    await mouse.addPointer(location: const Offset(0, 0));
    await mouse.moveTo(tester.getCenter(find.byType(HoverMetricTile)));
    await tester.pumpAndSettle();
    expect(revealHeight(), closeTo(100, 0.01));

    await mouse.moveTo(const Offset(0, 0));
    await tester.pumpAndSettle();
    expect(revealHeight(), closeTo(0, 0.01));
    await mouse.removePointer();
  });

  testWidgets('dashboard header fits a compact browser window', (tester) async {
    tester.view.physicalSize = const Size(800, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final state = AppState();
    addTearDown(state.dispose);
    await tester.pumpWidget(MyApp(state: state));
    expect(find.text('ATHENA'), findsOneWidget);
    expect(find.text('SETTINGS'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  test(
    'AppState ignores a second command while an upload is pending',
    () async {
      final api = BlockingUploadApi();
      final state = AppState(api: api);
      final first = state.uploadProfile('profile-one');
      final second = state.uploadProfile('profile-two');
      expect(api.uploadCalls, 1);
      expect(state.loading, isTrue);
      expect(state.uploading, isTrue);
      api.pending.complete(
        BenchSnapshot.fromJson({
          'connection': {'state': 'CONNECTED'},
          'history_counts': <String, int>{},
        }),
      );
      await Future.wait([first, second]);
      expect(state.loading, isFalse);
      expect(state.uploading, isFalse);
      state.dispose();
    },
  );

  testWidgets('upload indicator stays visible across tabs until confirmation', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1440, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final api = BlockingUploadApi();
    final state = AppState(api: api);
    addTearDown(state.dispose);
    await tester.pumpWidget(MyApp(state: state));
    final pending = state.uploadProfile('profile-one');
    await tester.pump();
    expect(find.text('Uploading profile…'), findsOneWidget);
    await tester.tap(find.text('PROFILE'));
    await tester.pump();
    expect(find.text('Uploading profile…'), findsOneWidget);
    api.pending.complete(
      BenchSnapshot.fromJson({
        'connection': {'state': 'CONNECTED'},
        'history_counts': <String, int>{},
      }),
    );
    await pending;
    await tester.pump();
    expect(find.text('Uploading profile…'), findsNothing);
  });

  test('failed upload clears progress and exposes the error', () async {
    final api = BlockingUploadApi();
    final state = AppState(api: api);
    final pending = state.uploadProfile('profile-one');
    api.pending.completeError(StateError('Checksum confirmation failed'));
    await pending;
    expect(state.uploading, isFalse);
    expect(state.loading, isFalse);
    expect(state.error, contains('Checksum confirmation failed'));
    state.dispose();
  });

  testWidgets('stale observations warn and cannot enable Start', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1440, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final state = AppState();
    addTearDown(state.dispose);
    state.snapshot = BenchSnapshot.fromJson({
      'connection': {'state': 'CONNECTED'},
      'bench_state': {'state': 'STOPPED'},
      'profile': {'id': 'previous'},
      'observation': {
        'fresh': false,
        'age_s': 10,
        'last_seen_at': '2026-09-26T00:00:00Z',
      },
    });
    await tester.pumpWidget(MyApp(state: state));
    expect(find.textContaining('Bench readings are stale.'), findsOneWidget);
    expect(
      tester
          .widget<FilledButton>(
            find.widgetWithText(FilledButton, '▶ Start 1 cycle'),
          )
          .onPressed,
      isNull,
    );
    expect(find.textContaining('Last bench observation:'), findsOneWidget);
  });
}
