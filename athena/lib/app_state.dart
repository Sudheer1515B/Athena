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
  bool _disposed = false;

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
    } catch (_) {
      error = 'Athena service is unavailable. Start the local backend.';
      _scheduleRetry();
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
    _subscription?.cancel();
    _live?.sink.close();
    _api.close();
    super.dispose();
  }
}
