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

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: widget.state,
    builder: (context, _) => Scaffold(
      body: Column(
        children: [
          _topBar(),
          Expanded(
            child: SingleChildScrollView(
              child: Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 1440),
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: IndexedStack(index: page.index, children: [
                      _dashboard(), ProfilePage(api: widget.state.api),
                      _history(), _settings(),
                    ]),
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
            _chip('SERVICE OFFLINE', Palette.critical)
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
        if (widget.state.error != null) ...[
          _banner(widget.state.error!),
          const SizedBox(height: 18),
        ],
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
          child: _empty('Events will appear when a bench session is recorded.'),
        ),
      ],
    );
  }

  Widget _tiles(bool narrow) {
    final tiles = [
      _tile(
        'Run state',
        widget.state.snapshot?.connectionState == 'CONNECTED'
            ? 'Unknown'
            : 'Disconnected',
        'No live bench state yet',
      ),
      _tile('Cycles completed', '—', 'Connect a bench for counters'),
      _tile('Current cycle', '—', 'No profile is running'),
      _tile('Total bench hours', '—', 'Reported by the bench'),
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

  Widget _channels() => BenchCard(
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
        _empty('Connect a bench to view its reported channels.'),
      ],
    ),
  );

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
                FilledButton(onPressed: null, child: const Text('▶ Start')),
                OutlinedButton(onPressed: null, child: const Text('Ⅱ Pause')),
                FilledButton(onPressed: null, child: const Text('■ Stop')),
                OutlinedButton(
                  onPressed: null,
                  child: const Text('Reset counters…'),
                ),
              ],
            ),
            const SizedBox(height: 10),
            const Text(
              'Controls become available after bench integration.',
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
          'WDR Protocol v1 · TCP port 3333',
          style: TextStyle(fontWeight: FontWeight.w600),
        ),
        const SizedBox(height: 8),
        const Text(
          'Connection setup arrives with the bench transport milestone.',
          style: TextStyle(color: Palette.secondary),
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
