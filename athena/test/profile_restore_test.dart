import 'package:athena/bench_api.dart';
import 'package:athena/profile_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class DraftApi extends BenchApi {
  DraftApi(this.profiles);
  final List<Map<String, dynamic>> profiles;
  @override
  Future<Map<String, dynamic>> recentSources() async => {
    'items': [
      {
        'id': 'source',
        'filename': 'RCOU.csv',
        'sha256':
            '8b9d117be6e4c6f9c316d880e06ba4c5c5a7d736807206b49a6a0c10209dfc1f',
        'inspection': {
          'columns': ['C1', 'C2', 'C3', 'C4'],
          'duration_us': 120000000,
          'gaps': [],
          'row_count': 100,
          'channels': {},
        },
      },
    ],
  };
  @override
  Future<Map<String, dynamic>> recentProfiles() async => {'items': profiles};
  @override
  Future<Map<String, dynamic>> sourcePreview(
    String id,
    List<String> channels,
    int start,
    int end,
  ) async => {'points': []};
  @override
  Future<Map<String, dynamic>> profilePreview(String id) async => {
    'points': [],
  };
}

Map<String, dynamic> savedDraft(int start, int end) => {
  'id': 'saved',
  'source_id': 'source',
  'settings': {
    'start_us': start * 1000000,
    'end_us': end * 1000000,
    'rate_hz': 25,
    'mapping': [
      for (var i = 0; i < 4; i++) {'source': 'C${i + 1}'},
    ],
  },
  'summary': {
    'frame_count': (end - start) * 25,
    'duration_s': end - start,
    'sum16': 123,
    'sha256': 'hash',
  },
};

void main() {
  for (final scenario in [
    ('fresh supplied source', <Map<String, dynamic>>[], '40', '100', '50'),
    (
      'older matching draft',
      [
        {'source_id': 'another'},
        savedDraft(40, 90),
      ],
      '40',
      '90',
      '25',
    ),
    ('intentional short draft', [savedDraft(0, 4)], '0', '4', '25'),
  ]) {
    testWidgets('restores ${scenario.$1}', (tester) async {
      tester.view.physicalSize = const Size(1440, 2000);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: ProfilePage(
                api: DraftApi(scenario.$2),
                benchConnected: false,
                benchBusy: false,
                transport: null,
                benchChannelCount: 4,
                benchMaxFrames: 8000,
                onUpload: (_) async {},
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      final fields = tester
          .widgetList<TextField>(find.byType(TextField))
          .toList();
      expect(
        fields
            .firstWhere((field) => field.decoration?.labelText == 'Start')
            .controller!
            .text,
        scenario.$3,
      );
      expect(
        fields
            .firstWhere((field) => field.decoration?.labelText == 'End')
            .controller!
            .text,
        scenario.$4,
      );
      expect(
        fields
            .firstWhere((field) => field.decoration?.suffixText == 'fps')
            .controller!
            .text,
        scenario.$5,
      );
      expect(tester.takeException(), isNull);
    });
  }
}
