import 'dart:math' as math;

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import 'bench_api.dart';
import 'theme.dart';

class ProfilePage extends StatefulWidget {
  const ProfilePage({
    super.key,
    required this.api,
    required this.benchConnected,
    required this.onUpload,
  });
  final BenchApi api;
  final bool benchConnected;
  final Future<void> Function(String) onUpload;

  @override
  State<ProfilePage> createState() => _ProfilePageState();
}

class _ProfilePageState extends State<ProfilePage> {
  final startController = TextEditingController(text: '40');
  final endController = TextEditingController(text: '44');
  final rateController = TextEditingController(text: '50');
  final outputs = <String?>[null, null, null, null];
  Map<String, dynamic>? source;
  Map<String, dynamic>? profile;
  Map<String, dynamic>? sourceTrace;
  Map<String, dynamic>? profileTrace;
  String? error;
  bool busy = false;

  @override
  void initState() {
    super.initState();
    restoreRecent();
  }

  Future<void> restoreRecent() async {
    try {
      final result = await Future.wait([
        widget.api.recentSources(),
        widget.api.recentProfiles(),
      ]);
      if (!mounted) return;
      final sourceItems = result[0]['items'] as List;
      final profileItems = result[1]['items'] as List;
      if (sourceItems.isEmpty) return;
      final latest = Map<String, dynamic>.from(sourceItems.first as Map);
      final saved =
          profileItems.isNotEmpty &&
              (profileItems.first as Map)['source_id'] == latest['id']
          ? Map<String, dynamic>.from(profileItems.first as Map)
          : null;
      final sourceColumns = ((latest['inspection'] as Map)['columns'] as List)
          .map((value) => value.toString())
          .toList();
      final duration =
          ((latest['inspection'] as Map)['duration_us'] as num).toDouble() /
          1000000;
      setState(() {
        source = latest;
        profile = saved;
        if (saved != null) {
          final settings = saved['settings'] as Map;
          startController.text = _decimal(
            (settings['start_us'] as num).toDouble() / 1000000,
          );
          endController.text = _decimal(
            (settings['end_us'] as num).toDouble() / 1000000,
          );
          rateController.text = settings['rate_hz'].toString();
          final map = settings['mapping'] as List;
          for (var i = 0; i < outputs.length; i++) {
            outputs[i] = i < map.length
                ? (map[i] as Map)['source']?.toString()
                : null;
          }
        } else {
          startController.text = '0';
          endController.text = _decimal(math.min(4, duration));
          for (var i = 0; i < outputs.length; i++) {
            outputs[i] = i < sourceColumns.length ? sourceColumns[i] : null;
          }
        }
      });
      if (saved != null) {
        final traces = await Future.wait([
          widget.api.sourcePreview(
            latest['id'].toString(),
            outputs.whereType<String>().toList(),
            (saved['settings'] as Map)['start_us'] as int,
            (saved['settings'] as Map)['end_us'] as int,
          ),
          widget.api.profilePreview(saved['id'].toString()),
        ]);
        if (mounted) {
          setState(() {
            sourceTrace = traces[0];
            profileTrace = traces[1];
          });
        }
      }
    } catch (_) {
      // The shell reports service availability; absence of recent drafts is harmless.
    }
  }

  @override
  void dispose() {
    startController.dispose();
    endController.dispose();
    rateController.dispose();
    super.dispose();
  }

  Map<String, dynamic>? get inspection =>
      source?['inspection'] as Map<String, dynamic>?;
  List<String> get columns =>
      (inspection?['columns'] as List? ?? []).map((e) => e.toString()).toList();

  Future<void> importFile() async {
    try {
      final picked = await FilePicker.platform.pickFiles(
        type: FileType.custom,
        allowedExtensions: ['csv'],
        withData: true,
      );
      if (picked == null || picked.files.isEmpty) return;
      final file = picked.files.single;
      final bytes = file.bytes;
      if (bytes == null) {
        throw StateError('The selected file could not be read.');
      }
      setState(() {
        busy = true;
        error = null;
      });
      final result = await widget.api.importSource(file.name, bytes);
      if (!mounted) return;
      final details = result['inspection'] as Map<String, dynamic>;
      final sourceColumns = (details['columns'] as List)
          .map((e) => e.toString())
          .toList();
      final duration = (details['duration_us'] as num).toDouble() / 1000000;
      final gaps = details['gaps'] as List;
      final start = gaps.isNotEmpty && duration >= 44 ? 40.0 : 0.0;
      final end = math.min(start + 4.0, duration);
      setState(() {
        source = result;
        profile = null;
        sourceTrace = null;
        profileTrace = null;
        startController.text = _decimal(start);
        endController.text = _decimal(end);
        for (var i = 0; i < outputs.length; i++) {
          outputs[i] = i < sourceColumns.length ? sourceColumns[i] : null;
        }
      });
    } catch (caught) {
      if (mounted) setState(() => error = _friendly(caught));
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> compile() async {
    if (source == null) return;
    try {
      final start = double.parse(startController.text.trim());
      final end = double.parse(endController.text.trim());
      final rate = int.parse(rateController.text.trim());
      if (!start.isFinite || !end.isFinite) {
        throw StateError('Enter finite trim times in seconds.');
      }
      final startUs = (start * 1000000).round();
      final endUs = (end * 1000000).round();
      setState(() {
        busy = true;
        error = null;
        profile = null;
        profileTrace = null;
      });
      final compiled = await widget.api.compileProfile({
        'source_id': source!['id'],
        'start_us': startUs,
        'end_us': endUs,
        'rate_hz': rate,
        'channel_count': 4,
        'maxframes': 8000,
        'mapping': [
          for (var i = 0; i < outputs.length; i++)
            {
              'output': i,
              'source': outputs[i],
              'label': outputs[i] ?? 'OUT$i',
              'min_us': 500,
              'max_us': 2500,
            },
        ],
      });
      final selected = outputs.whereType<String>().toList();
      final traces = await Future.wait([
        widget.api.sourcePreview(
          source!['id'].toString(),
          selected,
          startUs,
          endUs,
        ),
        widget.api.profilePreview(compiled['id'].toString()),
      ]);
      if (!mounted) return;
      setState(() {
        profile = compiled;
        sourceTrace = traces[0];
        profileTrace = traces[1];
      });
    } catch (caught) {
      if (mounted) setState(() => error = _friendly(caught));
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  String _friendly(Object error) =>
      error.toString().replaceFirst(RegExp(r'^(Bad state|Exception): '), '');
  String _decimal(double number) =>
      number.toStringAsFixed(3).replaceFirst(RegExp(r'\.?0+$'), '');

  void invalidateDraft() {
    setState(() {
      profile = null;
      profileTrace = null;
      sourceTrace = null;
      error = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    final narrow = MediaQuery.sizeOf(context).width < 1050;
    final left = Column(
      children: [
        _sourceCard(),
        const SizedBox(height: 18),
        _trimCard(),
        const SizedBox(height: 18),
        _uploadCard(),
      ],
    );
    final right = Column(
      children: [_mapCard(), const SizedBox(height: 18), _previewCard()],
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (error != null) ...[
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: const Color(0xFFFFECEC),
              border: Border.all(color: Palette.critical),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(
              error!,
              style: const TextStyle(color: Palette.critical),
            ),
          ),
          const SizedBox(height: 18),
        ],
        if (narrow)
          Column(children: [left, const SizedBox(height: 18), right])
        else
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SizedBox(width: 440, child: left),
              const SizedBox(width: 18),
              Expanded(child: right),
            ],
          ),
      ],
    );
  }

  Widget _sourceCard() => BenchCard(
    title: '1 · Source log',
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Container(
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(
            color: const Color(0xFFFAFAF8),
            border: Border.all(color: const Color(0xFFC9C8C3), width: 2),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Column(
            children: [
              Text(
                source?['filename']?.toString() ??
                    'Choose a recorded flight CSV',
                style: const TextStyle(fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 6),
              Text(
                source == null
                    ? 'TimeUS and C1–C16 columns · up to 50 MiB'
                    : '${inspection?['row_count']} rows · ${columns.length} source channels · '
                          '${_decimal((inspection?['duration_us'] as num).toDouble() / 1000000)} s',
                style: const TextStyle(color: Palette.muted, fontSize: 12.5),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 14),
              OutlinedButton(
                onPressed: busy ? null : importFile,
                child: Text(
                  source == null ? 'Choose CSV…' : 'Choose another CSV…',
                ),
              ),
            ],
          ),
        ),
        if (inspection != null) ...[
          const SizedBox(height: 12),
          Text(
            'Median sample interval ${inspection!['median_interval_us']} µs · '
            '${inspection!['effective_rate_hz']} samples/s',
            style: const TextStyle(color: Palette.secondary, fontSize: 12.5),
          ),
          const SizedBox(height: 8),
          Text(
            '${(inspection!['gaps'] as List).length} detected time gap(s). '
            'Select a window that does not cross a gap.',
            style: const TextStyle(color: Palette.secondary, fontSize: 12.5),
          ),
          const SizedBox(height: 8),
          Text(
            'Zero and invalid values are reported per source channel below. '
            'Mapped values outside 500–2500 µs block compilation.',
            style: const TextStyle(color: Palette.muted, fontSize: 12.5),
          ),
        ],
      ],
    ),
  );

  Widget _trimCard() => BenchCard(
    title: '2 · Resample & trim',
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'Frame rate · 10–100 frames/s',
          style: TextStyle(color: Palette.secondary),
        ),
        const SizedBox(height: 6),
        SizedBox(
          width: 100,
          child: TextField(
            controller: rateController,
            keyboardType: TextInputType.number,
            onChanged: (_) => invalidateDraft(),
            decoration: const InputDecoration(
              isDense: true,
              border: OutlineInputBorder(),
              suffixText: 'fps',
            ),
          ),
        ),
        const SizedBox(height: 12),
        const Text(
          'Trim · seconds from first sample',
          style: TextStyle(color: Palette.secondary),
        ),
        const SizedBox(height: 6),
        Row(
          children: [
            SizedBox(
              width: 105,
              child: TextField(
                controller: startController,
                keyboardType: const TextInputType.numberWithOptions(
                  decimal: true,
                ),
                onChanged: (_) => invalidateDraft(),
                decoration: const InputDecoration(
                  isDense: true,
                  border: OutlineInputBorder(),
                  labelText: 'Start',
                ),
              ),
            ),
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 10),
              child: Text('to'),
            ),
            SizedBox(
              width: 105,
              child: TextField(
                controller: endController,
                keyboardType: const TextInputType.numberWithOptions(
                  decimal: true,
                ),
                onChanged: (_) => invalidateDraft(),
                decoration: const InputDecoration(
                  isDense: true,
                  border: OutlineInputBorder(),
                  labelText: 'End',
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 10),
        const Text(
          'Reference bench draft: 4 outputs · maximum 8,000 frames. '
          'Live INFO will be checked before upload.',
          style: TextStyle(color: Palette.muted, fontSize: 12.5),
        ),
        const SizedBox(height: 10),
        if (inspection != null)
          FilledButton(
            onPressed: busy ? null : compile,
            child: const Text('Compile & validate'),
          ),
        if (profile != null) ...[
          const SizedBox(height: 10),
          Text(
            '${(profile!['summary'] as Map)['frame_count']} frames · '
            '${(profile!['summary'] as Map)['duration_s']} s per cycle',
            style: const TextStyle(fontWeight: FontWeight.w600),
          ),
        ],
      ],
    ),
  );

  Widget _mapCard() => BenchCard(
    title:
        '3 · Channel map · ${outputs.where((item) => item != null).length} of 4 mapped',
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Row(
          children: [
            SizedBox(width: 95, child: HeaderLabel('BENCH OUTPUT')),
            Expanded(child: HeaderLabel('SOURCE')),
            SizedBox(width: 90, child: HeaderLabel('MIN µs')),
            SizedBox(width: 90, child: HeaderLabel('MAX µs')),
            SizedBox(width: 95, child: HeaderLabel('INVALID')),
          ],
        ),
        const Divider(color: Palette.line),
        for (var i = 0; i < outputs.length; i++)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 5),
            child: Row(
              children: [
                SizedBox(
                  width: 95,
                  child: Text(
                    'OUT$i',
                    style: const TextStyle(fontWeight: FontWeight.w600),
                  ),
                ),
                Expanded(
                  child: DropdownButton<String?>(
                    value: outputs[i],
                    isExpanded: true,
                    underline: const SizedBox.shrink(),
                    items: [
                      const DropdownMenuItem<String?>(
                        value: null,
                        child: Text('Idle 1500 µs'),
                      ),
                      for (final name in columns)
                        DropdownMenuItem<String?>(
                          value: name,
                          child: Text(name),
                        ),
                    ],
                    onChanged: source == null
                        ? null
                        : (value) {
                            setState(() => outputs[i] = value);
                            invalidateDraft();
                          },
                  ),
                ),
                const SizedBox(width: 90, child: Text('500')),
                const SizedBox(width: 90, child: Text('2500')),
                SizedBox(
                  width: 95,
                  child: Text(
                    outputs[i] == null
                        ? '—'
                        : '${((inspection?['channels'] as Map?)?[outputs[i]] as Map?)?['invalid_count'] ?? 0}',
                    style: TextStyle(
                      color: outputs[i] == null
                          ? Palette.muted
                          : Palette.secondary,
                    ),
                  ),
                ),
              ],
            ),
          ),
        const SizedBox(height: 8),
        const Text(
          'Unmapped outputs stay at the fixed 1500 µs idle. '
          'A source can be assigned only once.',
          style: TextStyle(color: Palette.muted, fontSize: 12.5),
        ),
      ],
    ),
  );

  Widget _uploadCard() => BenchCard(
    title: '4 · Push to bench',
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (profile == null)
          const Text(
            'Compile a valid profile first.',
            style: TextStyle(color: Palette.muted),
          )
        else ...[
          Text(
            'Validated checksum · SUM16 ${(profile!['summary'] as Map)['sum16']}',
            style: const TextStyle(fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 4),
          Text(
            'SHA-256 ${(profile!['summary'] as Map)['sha256']}',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(color: Palette.secondary, fontSize: 12),
          ),
          const SizedBox(height: 10),
          OutlinedButton.icon(
            onPressed: () => launchUrl(
              widget.api.profileExportUri(profile!['id'].toString()),
            ),
            icon: const Icon(Icons.download, size: 18),
            label: const Text('Export compiled CSV'),
          ),
          const SizedBox(height: 8),
          FilledButton.icon(
            onPressed: busy || !widget.benchConnected
                ? null
                : () => widget.onUpload(profile!['id'].toString()),
            icon: const Icon(Icons.upload, size: 18),
            label: const Text('Upload to USB bench'),
          ),
          if (!widget.benchConnected) ...[
            const SizedBox(height: 8),
            const Text(
              'Connect the USB bench in Settings first.',
              style: TextStyle(color: Palette.muted, fontSize: 12.5),
            ),
          ],
        ],
      ],
    ),
  );

  Widget _previewCard() => BenchCard(
    title: 'Preview',
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (profile == null)
          const SizedBox(
            height: 220,
            child: Center(
              child: Text(
                'Import and compile a source log to preview commanded pulse widths.',
                style: TextStyle(color: Palette.muted),
              ),
            ),
          )
        else ...[
          const Text(
            'Source samples · selected window',
            style: TextStyle(color: Palette.secondary),
          ),
          const SizedBox(height: 7),
          SizedBox(
            height: 150,
            child: CustomPaint(
              painter: PulseTracePainter(_sourceSeries(), [
                for (var i = 0; i < outputs.length; i++)
                  if (outputs[i] != null) Palette.series[i],
              ]),
            ),
          ),
          const SizedBox(height: 12),
          const Text(
            'Compiled frames · zero-order hold',
            style: TextStyle(color: Palette.secondary),
          ),
          const SizedBox(height: 7),
          SizedBox(
            height: 150,
            child: CustomPaint(
              painter: PulseTracePainter(_profileSeries(), [
                for (var i = 0; i < outputs.length; i++)
                  if (outputs[i] != null) Palette.series[i],
              ]),
            ),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 14,
            children: [
              for (var i = 0; i < outputs.length; i++)
                if (outputs[i] != null)
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(width: 9, height: 9, color: Palette.series[i]),
                      const SizedBox(width: 5),
                      Text(
                        'OUT$i ${outputs[i]}',
                        style: const TextStyle(fontSize: 12.5),
                      ),
                    ],
                  ),
            ],
          ),
          const SizedBox(height: 10),
          const Text(
            'Preview is sampled for display. The saved profile retains every frame.',
            style: TextStyle(color: Palette.muted, fontSize: 12.5),
          ),
        ],
      ],
    ),
  );

  List<List<double>> _sourceSeries() {
    final points = sourceTrace?['points'] as List? ?? [];
    return [
      for (var i = 0; i < outputs.length; i++)
        if (outputs[i] != null)
          [
            for (final point in points)
              (((point as Map)['values'] as Map)[outputs[i]] as num).toDouble(),
          ],
    ];
  }

  List<List<double>> _profileSeries() {
    final points = profileTrace?['points'] as List? ?? [];
    return [
      for (var i = 0; i < outputs.length; i++)
        if (outputs[i] != null)
          [
            for (final point in points)
              (((point as Map)['values'] as List)[i] as num).toDouble(),
          ],
    ];
  }
}

class PulseTracePainter extends CustomPainter {
  PulseTracePainter(this.series, this.colors);
  final List<List<double>> series;
  final List<Color> colors;

  @override
  void paint(Canvas canvas, Size size) {
    final bounds = Rect.fromLTWH(
      34,
      8,
      math.max(1, size.width - 42),
      math.max(1, size.height - 25),
    );
    for (final value in [1000.0, 1500.0, 2000.0]) {
      final y = bounds.bottom - (value - 500) / 2000 * bounds.height;
      canvas.drawLine(
        Offset(bounds.left, y),
        Offset(bounds.right, y),
        Paint()
          ..color = const Color(0xFFECECEA)
          ..strokeWidth = 1,
      );
      final painter = TextPainter(
        text: TextSpan(
          text: value.toInt().toString(),
          style: const TextStyle(color: Palette.muted, fontSize: 10),
        ),
        textDirection: TextDirection.ltr,
      );
      painter.layout();
      painter.paint(canvas, Offset(0, y - painter.height / 2));
    }
    for (var channel = 0; channel < series.length; channel++) {
      final values = series[channel];
      if (values.length < 2) continue;
      final path = Path();
      for (var i = 0; i < values.length; i++) {
        final x = bounds.left + i / (values.length - 1) * bounds.width;
        final y =
            bounds.bottom -
            ((values[i] - 500) / 2000).clamp(0, 1) * bounds.height;
        if (i == 0) {
          path.moveTo(x, y);
        } else {
          path.lineTo(x, y);
        }
      }
      canvas.drawPath(
        path,
        Paint()
          ..color = colors[channel % colors.length]
          ..strokeWidth = 1.7
          ..style = PaintingStyle.stroke,
      );
    }
  }

  @override
  bool shouldRepaint(covariant PulseTracePainter oldDelegate) =>
      oldDelegate.series != series || oldDelegate.colors != colors;
}
