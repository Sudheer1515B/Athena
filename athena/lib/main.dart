import 'package:flutter/material.dart';

import 'app_state.dart';
import 'profile_page.dart';
import 'theme.dart';

void main() => runApp(const MyApp());

class MyApp extends StatefulWidget {
  const MyApp({super.key, this.state});

  final AppState? state;

  @override
  State<MyApp> createState() => _MyAppState();
}

class _MyAppState extends State<MyApp> {
  late final AppState state;

  @override
  void initState() {
    super.initState();
    state = widget.state ?? AppState();
    if (widget.state == null) state.connect();
  }

  @override
  void dispose() {
    if (widget.state == null) state.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Athena · Replay Bench',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      useMaterial3: true,
      scaffoldBackgroundColor: Palette.background,
      fontFamily: 'Roboto',
      colorScheme: ColorScheme.fromSeed(seedColor: Palette.brand),
    ),
    home: AthenaShell(state: state),
  );
}

enum AthenaPage { dashboard, profile, history, settings }

class AthenaShell extends StatefulWidget {
  const AthenaShell({super.key, required this.state});
  final AppState state;

  @override
  State<AthenaShell> createState() => _AthenaShellState();
}

class _AthenaShellState extends State<AthenaShell> {
  AthenaPage page = AthenaPage.dashboard;
  final usbPort = TextEditingController(text: '/dev/cu.usbserial-0001');

  @override
  void dispose() {
    usbPort.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: widget.state,
    builder: (context, _) => Scaffold(
      body: Column(
        children: [
          _topBar(),
          if (widget.state.error != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(24, 12, 24, 0),
              child: _banner(widget.state.error!),
            ),
          Expanded(
            child: SingleChildScrollView(
              child: Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 1440),
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: IndexedStack(
                      index: page.index,
                      children: [
                        _dashboard(),
                        ProfilePage(
                          api: widget.state.api,
                          benchConnected:
                              widget.state.snapshot?.connectionState ==
                              'CONNECTED',
                          transport: widget
                              .state
                              .snapshot
                              ?.connection['transport']
                              ?.toString(),
                          onUpload: widget.state.uploadProfile,
                        ),
                        _history(),
                        _settings(),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    ),
  );

  Widget _topBar() {
    final connected = widget.state.snapshot?.connectionState == 'CONNECTED';
    return Container(
      height: 56,
      color: const Color(0xFF111111),
      padding: const EdgeInsets.symmetric(horizontal: 24),
      child: Row(
        children: [
          const Text(
            'WELKINRIM',
            style: TextStyle(
              color: Colors.white,
              fontWeight: FontWeight.w800,
              letterSpacing: .4,
            ),
          ),
          const SizedBox(width: 6),
          const Text(
            'Replay Bench',
            style: TextStyle(
              color: Color(0xFFF26A68),
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(width: 32),
          for (final item in AthenaPage.values) _navItem(item),
          const Spacer(),
          if (widget.state.error != null)
            _chip('CHECK MESSAGE', Palette.critical)
          else
            _chip(
              connected ? 'BENCH CONNECTED' : 'BENCH DISCONNECTED',
              connected ? Palette.good : Palette.muted,
            ),
        ],
      ),
    );
  }

  Widget _navItem(AthenaPage item) {
    final selected = item == page;
    return Padding(
      padding: const EdgeInsets.only(right: 4),
      child: TextButton(
        onPressed: () => setState(() => page = item),
        style: TextButton.styleFrom(
          foregroundColor: selected ? Colors.white : const Color(0xFFBBBBBB),
          backgroundColor: selected ? const Color(0xFF2A2A2A) : null,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
        ),
        child: Text(switch (item) {
          AthenaPage.dashboard => 'Dashboard',
          AthenaPage.profile => 'Profile',
          AthenaPage.history => 'History',
          AthenaPage.settings => 'Settings',
        }),
      ),
    );
  }

  Widget _chip(String label, Color dot) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
    decoration: BoxDecoration(
      border: Border.all(color: const Color(0xFF333333)),
      borderRadius: BorderRadius.circular(20),
    ),
    child: Row(
      children: [
        Container(
          width: 9,
          height: 9,
          decoration: BoxDecoration(color: dot, shape: BoxShape.circle),
        ),
        const SizedBox(width: 7),
        Text(
          label,
          style: const TextStyle(color: Color(0xFFDDDDDD), fontSize: 12.5),
        ),
      ],
    ),
  );

  Widget _dashboard() {
    final isNarrow = MediaQuery.sizeOf(context).width < 1050;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _tiles(isNarrow),
        const SizedBox(height: 18),
        if (isNarrow)
          Column(
            children: [_channels(), const SizedBox(height: 18), _rightColumn()],
          )
        else
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(child: _channels()),
              const SizedBox(width: 18),
              SizedBox(width: 700, child: _rightColumn()),
            ],
          ),
        const SizedBox(height: 18),
        BenchCard(
          title: 'Recent events',
          child: widget.state.snapshot?.recentEvents.isNotEmpty == true
              ? Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    for (final event in widget.state.snapshot!.recentEvents)
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: 3),
                        child: Text(event),
                      ),
                  ],
                )
              : _empty('No events received yet.'),
        ),
      ],
    );
  }

  Widget _tiles(bool narrow) {
    final snapshot = widget.state.snapshot;
    final status = snapshot?.benchState;
    final counters = snapshot?.counters;
    final connected = snapshot?.connectionState == 'CONNECTED';
    final runSeconds = int.tryParse(counters?['run_s']?.toString() ?? '');
    final tiles = [
      _tile(
        'Run state',
        connected
            ? (status?['state']?.toString() ?? 'Unknown')
            : 'Disconnected',
        connected
            ? (snapshot?.connection['transport'] == 'SIMULATOR'
                  ? 'Local simulator'
                  : 'USB bench')
            : 'Connect in Settings',
      ),
      _tile(
        'Cycles completed',
        counters?['cycles']?.toString() ?? '—',
        'Lifetime bench total',
      ),
      _tile(
        'Current cycle',
        status?['cycle']?.toString() ?? '—',
        'Current run',
      ),
      _tile(
        'Total bench hours',
        runSeconds == null ? '—' : (runSeconds / 3600).toStringAsFixed(3),
        'RUNNING time from bench',
      ),
    ];
    if (narrow) {
      return Wrap(
        spacing: 18,
        runSpacing: 18,
        children: [for (final tile in tiles) SizedBox(width: 290, child: tile)],
      );
    }
    return Row(
      children: [
        for (var i = 0; i < tiles.length; i++) ...[
          if (i != 0) const SizedBox(width: 18),
          Expanded(child: tiles[i]),
        ],
      ],
    );
  }

  Widget _tile(String label, String value, String detail) => BenchCard(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label.toUpperCase(),
          style: const TextStyle(
            color: Palette.secondary,
            fontSize: 12.5,
            letterSpacing: .6,
          ),
        ),
        const SizedBox(height: 7),
        Text(
          value,
          style: const TextStyle(
            color: Palette.ink,
            fontSize: 30,
            fontWeight: FontWeight.w700,
          ),
        ),
        Text(
          detail,
          style: const TextStyle(color: Palette.muted, fontSize: 12.5),
        ),
      ],
    ),
  );

  Widget _channels() {
    final snapshot = widget.state.snapshot;
    final live = snapshot?.benchState?['us']?.toString().split(',') ?? [];
    final active = snapshot?.counters?['active_s']?.toString().split(',') ?? [];
    return BenchCard(
      title: 'Channels',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Expanded(child: HeaderLabel('NAME')),
              SizedBox(width: 76, child: HeaderLabel('LIVE µs')),
              SizedBox(width: 72, child: HeaderLabel('IDLE µs')),
              SizedBox(width: 66, child: HeaderLabel('ACTIVE h')),
            ],
          ),
          const Divider(color: Palette.line),
          if (live.isEmpty)
            _empty('Connect a bench to view its reported channels.')
          else
            for (var i = 0; i < live.length; i++)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 6),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        'OUT$i',
                        style: const TextStyle(fontWeight: FontWeight.w600),
                      ),
                    ),
                    SizedBox(width: 76, child: Text(live[i])),
                    const SizedBox(width: 72, child: Text('1500')),
                    SizedBox(
                      width: 66,
                      child: Text(
                        i < active.length
                            ? ((int.tryParse(active[i]) ?? 0) / 3600)
                                  .toStringAsFixed(3)
                            : '—',
                      ),
                    ),
                  ],
                ),
              ),
        ],
      ),
    );
  }

  Widget _rightColumn() => Column(
    children: [
      BenchCard(
        title: 'Controls',
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Wrap(
              spacing: 10,
              runSpacing: 10,
              children: [
                FilledButton(
                  onPressed:
                      widget.state.loading ||
                          widget.state.snapshot?.profile == null ||
                          widget.state.snapshot?.benchState?['state'] !=
                              'STOPPED'
                      ? null
                      : () => widget.state.control('start', cycles: 1),
                  child: const Text('▶ Start 1 cycle'),
                ),
                OutlinedButton(
                  onPressed:
                      widget.state.loading ||
                          widget.state.snapshot?.benchState?['state'] !=
                              'RUNNING'
                      ? null
                      : () => widget.state.control('pause'),
                  child: const Text('Ⅱ Pause'),
                ),
                OutlinedButton(
                  onPressed:
                      widget.state.loading ||
                          widget.state.snapshot?.benchState?['state'] !=
                              'PAUSED'
                      ? null
                      : () => widget.state.control('resume'),
                  child: const Text('▶ Resume'),
                ),
                FilledButton(
                  onPressed:
                      widget.state.loading ||
                          widget.state.snapshot?.connectionState != 'CONNECTED'
                      ? null
                      : () => widget.state.control('stop'),
                  child: const Text('■ Stop'),
                ),
              ],
            ),
            const SizedBox(height: 10),
            const Text(
              'Upload a compiled profile, then start a finite cycle. Verify actuator power, common ground and mechanical clearance first.',
              style: TextStyle(color: Palette.muted, fontSize: 12.5),
            ),
          ],
        ),
      ),
      const SizedBox(height: 18),
      BenchCard(
        title: 'Live traces · this cycle',
        child: SizedBox(
          height: 230,
          child: Center(
            child: _empty('No commanded PWM trace is available yet.'),
          ),
        ),
      ),
    ],
  );

  Widget _history() => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      BenchCard(
        title: 'Range',
        child: _empty(
          'Date filtering becomes available with recorded sessions.',
        ),
      ),
      const SizedBox(height: 18),
      BenchCard(
        title: 'Active hours per channel',
        child: _empty('No counter observations recorded.'),
      ),
      const SizedBox(height: 18),
      BenchCard(title: 'Sessions', child: _empty('No sessions recorded.')),
      const SizedBox(height: 18),
      BenchCard(title: 'Events', child: _empty('No events recorded.')),
    ],
  );

  Widget _settings() => BenchCard(
    title: 'Bench connection',
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'WDR Protocol v1 · USB bench or local simulator',
          style: TextStyle(fontWeight: FontWeight.w600),
        ),
        const SizedBox(height: 8),
        const Text(
          'ESP32 USB port on this Mac',
          style: TextStyle(color: Palette.secondary),
        ),
        const SizedBox(height: 8),
        SizedBox(
          width: 330,
          child: TextField(
            controller: usbPort,
            decoration: const InputDecoration(
              border: OutlineInputBorder(),
              isDense: true,
            ),
          ),
        ),
        const SizedBox(height: 10),
        Wrap(
          spacing: 8,
          children: [
            FilledButton(
              onPressed: widget.state.loading
                  ? null
                  : () => widget.state.connectUsb(usbPort.text.trim()),
              child: const Text('Connect USB bench'),
            ),
            OutlinedButton(
              onPressed:
                  widget.state.snapshot?.connectionState == 'CONNECTED' &&
                      !widget.state.loading
                  ? widget.state.disconnectBench
                  : null,
              child: const Text('Disconnect'),
            ),
          ],
        ),
        const SizedBox(height: 14),
        const Text(
          'Simulator: run the supplied serve-sim tool on this Mac (TCP 3333).',
          style: TextStyle(color: Palette.secondary),
        ),
        const SizedBox(height: 8),
        FilledButton.tonal(
          onPressed: widget.state.loading
              ? null
              : widget.state.connectSimulator,
          child: const Text('Connect local simulator'),
        ),
        const SizedBox(height: 8),
        Text(
          'Bench: ${widget.state.snapshot?.connection['bench'] ?? 'not connected'}',
          style: const TextStyle(color: Palette.secondary),
        ),
        const SizedBox(height: 8),
        const Text(
          'Opening USB has reset this ESP32 during testing. Connect only when stopping the bench is safe.',
          style: TextStyle(color: Palette.critical, fontSize: 12.5),
        ),
        const SizedBox(height: 12),
        Text(
          'Service: ${widget.state.error == null ? 'Available' : 'Unavailable'}',
          style: const TextStyle(color: Palette.secondary),
        ),
      ],
    ),
  );

  Widget _banner(String message) => Container(
    padding: const EdgeInsets.all(14),
    decoration: BoxDecoration(
      color: const Color(0xFFFFECEC),
      border: Border.all(color: Palette.critical),
      borderRadius: BorderRadius.circular(8),
    ),
    child: Text(message, style: const TextStyle(color: Palette.critical)),
  );

  Widget _empty(String text) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 15),
    child: Text(
      text,
      style: const TextStyle(color: Palette.muted, fontSize: 13),
    ),
  );
}
