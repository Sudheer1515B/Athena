import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import 'bench_api.dart';

class AppState extends ChangeNotifier {
  AppState({BenchApi? api}) : _api = api ?? BenchApi();

  final BenchApi _api;
  BenchApi get api => _api;
  BenchSnapshot? snapshot;
  String? error;
  bool loading = false;
  WebSocketChannel? _live;
  StreamSubscription<dynamic>? _subscription;
  Timer? _retry;
  Timer? _poll;
  bool _disposed = false;
  bool _refreshing = false;

  Future<void> connect() async {
    if (_disposed) return;
    loading = true;
    error = null;
    notifyListeners();
    try {
      snapshot = await _api.fetchSnapshot();
      error = null;
      notifyListeners();
      _openLive();
      _poll ??= Timer.periodic(const Duration(seconds: 1), (_) => refresh());
    } catch (_) {
      error = 'Athena service is unavailable. Start the local backend.';
      _scheduleRetry();
    } finally {
      loading = false;
      if (!_disposed) notifyListeners();
    }
  }

  Future<void> refresh() async {
    if (_disposed || loading || _refreshing) return;
    _refreshing = true;
    try {
      snapshot = await _api.fetchSnapshot();
      if (error?.startsWith('Athena service is unavailable') == true ||
          error?.startsWith('USB bench did not respond') == true) {
        error = null;
      }
      if (!_disposed) notifyListeners();
    } catch (caught) {
      error = caught.toString().replaceFirst(
        RegExp(r'^(Bad state|Exception): '),
        '',
      );
      if (!_disposed) notifyListeners();
    } finally {
      _refreshing = false;
    }
  }

  Future<void> connectUsb(String port) => _operate(() => _api.connectUsb(port));
  Future<void> connectSimulator() => _operate(_api.connectSimulator);
  Future<void> disconnectBench() => _operate(_api.disconnectBench);
  Future<void> uploadProfile(String id) =>
      _operate(() => _api.uploadProfile(id));
  Future<void> control(String action, {int cycles = 1}) =>
      _operate(() => _api.control(action, cycles: cycles));

  Future<void> _operate(Future<BenchSnapshot> Function() operation) async {
    loading = true;
    error = null;
    notifyListeners();
    try {
      snapshot = await operation();
    } catch (caught) {
      error = caught.toString().replaceFirst(
        RegExp(r'^(Bad state|Exception): '),
        '',
      );
    } finally {
      loading = false;
      if (!_disposed) notifyListeners();
    }
  }

  void _openLive() {
    if (_disposed) return;
    try {
      _live = _api.openLive();
      _subscription = _live!.stream.listen(
        (message) {
          try {
            final data = jsonDecode(message.toString()) as Map<String, dynamic>;
            if (data['type'] == 'snapshot' && data['payload'] is Map) {
              snapshot = BenchSnapshot.fromJson(
                Map<String, dynamic>.from(data['payload'] as Map),
              );
              error = null;
              if (!_disposed) notifyListeners();
            }
          } catch (_) {
            error = 'The live stream sent an invalid update.';
            if (!_disposed) notifyListeners();
          }
        },
        onError: (_) {
          error = 'Live updates disconnected. Reconnecting…';
          if (!_disposed) notifyListeners();
          _scheduleRetry();
        },
        onDone: () {
          if (!_disposed) _scheduleRetry();
        },
      );
    } catch (_) {
      _scheduleRetry();
    }
  }

  void _scheduleRetry() {
    if (_disposed || _retry?.isActive == true) return;
    _retry = Timer(const Duration(seconds: 3), connect);
  }

  @override
  void dispose() {
    _disposed = true;
    _retry?.cancel();
    _poll?.cancel();
    _subscription?.cancel();
    _live?.sink.close();
    _api.close();
    super.dispose();
  }
}
