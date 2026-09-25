import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import 'app_state.dart';
import 'bench_api.dart';
import 'theme.dart';

String _known(Object? value) {
  final text = value?.toString() ?? '';
  return text.isEmpty ? 'Unknown' : text;
}

String _localTime(Object? value) {
  final parsed = DateTime.tryParse(value?.toString() ?? '')?.toLocal();
  if (parsed == null) return 'Unknown';
  String two(int number) => number.toString().padLeft(2, '0');
  return '${parsed.year}-${two(parsed.month)}-${two(parsed.day)} '
      '${two(parsed.hour)}:${two(parsed.minute)}:${two(parsed.second)} local';
}

String _hours(Object? seconds) {
  if (seconds is! num) return 'Unknown';
  return '${(seconds / 3600).toStringAsFixed(4)} h';
}

List<int>? _activeSeconds(Map<String, dynamic> session) {
  final delta = session['delta'];
  final active = delta is Map ? delta['active_s'] : null;
  if (active is! List) return null;
  return [
    for (final value in active)
      if (value is num) value.toInt(),
  ];
}

class HistoryPage extends StatefulWidget {
  const HistoryPage({super.key, required this.state});

  final AppState state;

  @override
  State<HistoryPage> createState() => _HistoryPageState();
}

class _HistoryPageState extends State<HistoryPage> {
  final from = TextEditingController();
  final through = TextEditingController();
  int? selectedChannel;

  @override
  void dispose() {
    from.dispose();
    through.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final sessions = widget.state.historySessions;
    final channelCount = sessions.fold<int>(0, (count, session) {
      final reported = session['channel_count'];
      return count > (reported is num ? reported.toInt() : 0)
          ? count
          : (reported is num ? reported.toInt() : 0);
    });
    final channel = selectedChannel != null && selectedChannel! < channelCount
        ? selectedChannel
        : null;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        BenchCard(
          title: 'Recorded bench history',
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Date filters use UTC. Timestamps below are shown in local time. '
                'Channel selection changes the chart and session details; '
                'events have no channel attribution.',
                style: TextStyle(color: Palette.secondary, fontSize: 12),
              ),
              const SizedBox(height: 12),
              Wrap(
                spacing: 10,
                runSpacing: 8,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  SizedBox(
                    width: 150,
                    child: TextField(
                      controller: from,
                      decoration: const InputDecoration(
                        labelText: 'From YYYY-MM-DD',
                        border: OutlineInputBorder(),
                        isDense: true,
                      ),
                    ),
                  ),
                  SizedBox(
                    width: 160,
                    child: TextField(
                      controller: through,
                      decoration: const InputDecoration(
                        labelText: 'Through YYYY-MM-DD',
                        border: OutlineInputBorder(),
                        isDense: true,
                      ),
                    ),
                  ),
                  DropdownButton<int?>(
                    value: channel,
                    items: [
                      const DropdownMenuItem<int?>(
                        value: null,
                        child: Text('All channels'),
                      ),
                      for (var index = 0; index < channelCount; index++)
                        DropdownMenuItem<int?>(
                          value: index,
                          child: Text('OUT$index'),
                        ),
                    ],
                    onChanged: (value) =>
                        setState(() => selectedChannel = value),
                  ),
                  FilledButton.tonal(
                    onPressed: widget.state.historyLoading
                        ? null
                        : () => widget.state.loadHistory(
                            fromDate: from.text.trim(),
                            throughDate: through.text.trim(),
                          ),
                    child: const Text('Apply range'),
                  ),
                  OutlinedButton(
                    onPressed: widget.state.historyLoading
                        ? null
                        : () => widget.state.loadHistory(),
                    child: const Text('Refresh'),
                  ),
                  OutlinedButton.icon(
                    onPressed: () => launchUrl(
                      widget.state.api.historyExportUri(
                        from.text.trim(),
                        through.text.trim(),
                      ),
                    ),
                    icon: const Icon(Icons.download, size: 18),
                    label: const Text('Export CSV'),
                  ),
                ],
              ),
            ],
          ),
        ),
        if (widget.state.historyError != null) ...[
          const SizedBox(height: 12),
          Text(
            widget.state.historyError!,
            style: const TextStyle(color: Palette.critical),
          ),
        ],
        const SizedBox(height: 18),
        _ActiveHoursChart(sessions: sessions, channel: channel),
        const SizedBox(height: 18),
        BenchCard(
          title: 'Sessions · ${sessions.length} loaded',
          child: sessions.isEmpty
              ? const Text('No sessions recorded for this range.')
              : Column(
                  children: [
                    for (final session in sessions)
                      _SessionTile(
                        key: ValueKey(
                          '${session['id']}/${session['status']}/'
                          '${session['observation_count']}',
                        ),
                        session: session,
                        channel: channel,
                        api: widget.state.api,
                      ),
                  ],
                ),
        ),
        const SizedBox(height: 18),
        BenchCard(
          title: 'Events · ${widget.state.historyEvents.length} loaded',
          child: widget.state.historyEvents.isEmpty
              ? const Text('No events recorded for this range.')
              : SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: DataTable(
                    columns: const [
                      DataColumn(label: Text('Observed time')),
                      DataColumn(label: Text('Event')),
                      DataColumn(label: Text('Confidence')),
                      DataColumn(label: Text('Session ID')),
                    ],
                    rows: [
                      for (final event in widget.state.historyEvents)
                        DataRow(
                          cells: [
                            DataCell(Text(_localTime(event['received_at']))),
                            DataCell(Text(_known(event['kind']))),
                            DataCell(Text(_known(event['confidence']))),
                            DataCell(
                              SelectableText(_known(event['session_id'])),
                            ),
                          ],
                        ),
                    ],
                  ),
                ),
        ),
      ],
    );
  }
}

class _ActiveHoursChart extends StatelessWidget {
  const _ActiveHoursChart({required this.sessions, required this.channel});

  final List<Map<String, dynamic>> sessions;
  final int? channel;

  @override
  Widget build(BuildContext context) {
    final count = sessions.fold<int>(0, (current, session) {
      final active = _activeSeconds(session);
      return active != null && active.length > current
          ? active.length
          : current;
    });
    final totals = List<int>.filled(count, 0);
    var excluded = 0;
    for (final session in sessions) {
      final active = _activeSeconds(session);
      if (active == null) {
        excluded++;
        continue;
      }
      for (var index = 0; index < active.length; index++) {
        totals[index] += active[index];
      }
    }
    final channels = [
      for (var index = 0; index < totals.length; index++)
        if (channel == null || channel == index) index,
    ];
    final maximum = totals.fold<int>(0, (a, b) => a > b ? a : b);
    final linkGaps = sessions
        .where((session) => session['has_link_gap'] == true)
        .length;
    return BenchCard(
      title: 'Observed active hours by channel',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (channels.isEmpty)
            const Text(
              'Unknown — no sessions have two usable counter observations.',
            ),
          for (final index in channels) ...[
            Row(
              children: [
                SizedBox(width: 60, child: Text('OUT$index')),
                Expanded(
                  child: LinearProgressIndicator(
                    value: maximum == 0 ? 0 : totals[index] / maximum,
                    minHeight: 13,
                    backgroundColor: Palette.line,
                    color: Palette.series[index % Palette.series.length],
                  ),
                ),
                SizedBox(
                  width: 95,
                  child: Text(
                    _hours(totals[index]),
                    textAlign: TextAlign.right,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 9),
          ],
          Text(
            'Sum of whole-session bench counter deltas for the ${sessions.length} loaded sessions '
            '(sessions may overlap the selected UTC dates). '
            '${excluded == 0 ? 'No unknown session deltas.' : '$excluded unknown session deltas excluded.'} '
            '${linkGaps == 0 ? '' : '$linkGaps sessions have link gaps; intermediate events are unknown. '}Only loaded sessions are included.',
            style: const TextStyle(color: Palette.secondary, fontSize: 12),
          ),
        ],
      ),
    );
  }
}

class _SessionTile extends StatefulWidget {
  const _SessionTile({
    super.key,
    required this.session,
    required this.channel,
    required this.api,
  });

  final Map<String, dynamic> session;
  final int? channel;
  final BenchApi api;

  @override
  State<_SessionTile> createState() => _SessionTileState();
}

class _SessionTileState extends State<_SessionTile> {
  Future<Map<String, dynamic>>? detail;

  @override
  Widget build(BuildContext context) {
    final session = widget.session;
    final delta = session['delta'] as Map?;
    final active = _activeSeconds(session);
    final channel = widget.channel;
    return Material(
      color: Colors.transparent,
      child: ExpansionTile(
        tilePadding: EdgeInsets.zero,
        title: Text(
          '${_known(session['bench_label'])} · ${_localTime(session['started_at'])}',
          style: const TextStyle(fontWeight: FontWeight.w600),
        ),
        subtitle: Text(
          '${_known(session['status'])} · target ${_known(session['target_cycles'])} · '
          '${delta?['cycles'] ?? 'Unknown'} cycle delta · '
          '${_hours(delta?['run_s'])} bench running · '
          '${channel == null ? (active == null ? 'active hours Unknown' : 'active hours for ${active.length} channels') : 'OUT$channel ${active != null && channel < active.length ? _hours(active[channel]) : 'Unknown'}'}'
          '${session['has_link_gap'] == true ? ' · link gap' : ''}',
        ),
        onExpansionChanged: (expanded) {
          if (expanded) {
            setState(() {
              detail = widget.api.historySession(session['id'].toString());
            });
          }
        },
        children: [
          if (detail != null)
            FutureBuilder<Map<String, dynamic>>(
              future: detail,
              builder: (context, snapshot) {
                if (snapshot.hasError) {
                  return Text(
                    'Could not load session details: ${snapshot.error}',
                  );
                }
                if (!snapshot.hasData) return const LinearProgressIndicator();
                return _SessionDetail(detail: snapshot.data!, channel: channel);
              },
            ),
        ],
      ),
    );
  }
}

class _SessionDetail extends StatelessWidget {
  const _SessionDetail({required this.detail, required this.channel});

  final Map<String, dynamic> detail;
  final int? channel;

  @override
  Widget build(BuildContext context) {
    final settings = detail['profile_settings'] as Map?;
    final mapping = settings?['mapping'] as List?;
    final observations = detail['counter_observations'] as List? ?? const [];
    final events = detail['events'] as List? ?? const [];
    final delta = detail['delta'] as Map?;
    final active = delta?['active_s'] as List?;
    final capabilities = detail['bench_capabilities'] as Map?;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 18),
      color: Palette.background,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (detail['status'] == 'UNCONFIRMED' ||
              detail['has_link_gap'] == true)
            const Padding(
              padding: EdgeInsets.only(bottom: 10),
              child: Text(
                'Uncertain coverage: the controller lost contact. Bench counters '
                'can bracket the gap, but intermediate events are unknown.',
                style: TextStyle(
                  color: Palette.critical,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          if (detail['counter_epoch_changed'] == true)
            const Text(
              'Counter reset or replacement suspected. Session deltas are unknown.',
              style: TextStyle(color: Palette.critical),
            ),
          _fact('Start observed', _localTime(detail['started_at'])),
          _fact('End observed', _localTime(detail['ended_at'])),
          _fact('Stop cause', _known(detail['stop_cause'])),
          _fact('Session confidence', _known(detail['identity_confidence'])),
          _fact('Cycle target', _known(detail['target_cycles'])),
          _fact('Observed cycle delta', _known(delta?['cycles'])),
          _fact('Observed bench running', _hours(delta?['run_s'])),
          for (var index = 0; index < (active?.length ?? 0); index++)
            if (channel == null || channel == index)
              _fact('OUT$index active', _hours(active![index])),
          if (delta == null)
            _fact(
              'Counter delta',
              'Unknown — insufficient observations or changed counter epoch',
            ),
          const Divider(height: 22),
          _fact(
            'Bench',
            '${_known(detail['bench_label'])} · ${_known(detail['bench_mode'])}',
          ),
          _fact('Bench address', _known(detail['bench_host'])),
          _fact('Bench ID', _known(detail['bench_id'])),
          _fact(
            'Latest saved WDR capabilities',
            capabilities == null
                ? 'Unknown'
                : 'protocol ${_known(capabilities['proto'])}, '
                      '${_known(capabilities['ch'])} channels, '
                      'max ${_known(capabilities['maxframes'])} frames',
          ),
          _fact('Source file', _known(detail['source_name'])),
          _fact('Source SHA-256', _known(detail['source_sha256'])),
          _fact('Profile ID', _known(detail['profile_id'])),
          _fact('Profile SHA-256', _known(detail['profile_sha256'])),
          _fact('Profile SUM16', _known(detail['profile_sum16'])),
          _fact(
            'Profile frames/rate',
            detail['profile_frame_count'] == null
                ? 'Unknown'
                : '${detail['profile_frame_count']} frames · ${detail['profile_rate_hz']} Hz',
          ),
          _fact(
            'Source window',
            settings == null
                ? 'Unknown'
                : '${settings['start_us']}–${settings['end_us']} µs',
          ),
          if (mapping == null) _fact('Output mapping and limits', 'Unknown'),
          for (final entry in mapping ?? const [])
            if (entry is Map && (channel == null || entry['output'] == channel))
              _fact(
                'OUT${entry['output']} mapping',
                '${_known(entry['source'])} · ${_known(entry['label'])} · '
                    '${_known(entry['min_us'])}–${_known(entry['max_us'])} µs'
                    '${entry['serial'] == null ? '' : ' · serial ${entry['serial']}'}',
              ),
          const Divider(height: 22),
          Text(
            'Counter observations · ${observations.length}',
            style: const TextStyle(fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 4),
          const Text(
            'Bench-reported lifetime totals sampled by Athena; not every PWM frame.',
            style: TextStyle(color: Palette.secondary, fontSize: 12),
          ),
          if (observations.isEmpty)
            const Text('No counter observations saved.'),
          if (observations.isNotEmpty)
            SizedBox(
              height: 210,
              child: ListView.builder(
                itemCount: observations.length,
                itemBuilder: (context, index) {
                  final sample = observations[index] as Map;
                  final sampleActive = sample['active_s'] as List?;
                  final selected = channel;
                  final activeText = selected == null
                      ? (sampleActive
                                ?.asMap()
                                .entries
                                .map((item) => 'OUT${item.key} ${item.value}s')
                                .join(', ') ??
                            'Unknown')
                      : (sampleActive != null && selected < sampleActive.length
                            ? 'OUT$selected ${sampleActive[selected]}s'
                            : 'OUT$selected Unknown');
                  return Padding(
                    padding: const EdgeInsets.symmetric(vertical: 3),
                    child: Text(
                      '${_localTime(sample['observed_at'])} · '
                      '${sample['cycles']} cycles · ${sample['run_s']} running s · '
                      'uptime ${sample['uptime_s']} s · '
                      '$activeText',
                      style: const TextStyle(fontSize: 12),
                    ),
                  );
                },
              ),
            ),
          const SizedBox(height: 8),
          Text(
            'Session events · ${events.length}',
            style: const TextStyle(fontWeight: FontWeight.w600),
          ),
          for (final event in events)
            if (event is Map)
              Text(
                '${_localTime(event['received_at'])} · '
                '${_known(event['kind'])} · ${_known(event['confidence'])}',
              ),
        ],
      ),
    );
  }

  Widget _fact(String label, String value) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 2),
    child: SelectableText('$label: $value'),
  );
}
