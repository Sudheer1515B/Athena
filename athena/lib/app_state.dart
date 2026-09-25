import 'dart:async';

import 'package:flutter/foundation.dart';

import 'bench_api.dart';

class AppState extends ChangeNotifier {
  AppState({BenchApi? api}) : _api = api ?? BenchApi();

  final BenchApi _api;
  BenchApi get api => _api;
  BenchSnapshot? snapshot;
  String? error;
  bool loading = false;
  bool historyLoading = false;
  String? historyError;
  List<Map<String, dynamic>> historySessions = const [];
  List<Map<String, dynamic>> historyEvents = const [];
  String? historyFromDate;
  String? historyThroughDate;
  Timer? _retry;
  Timer? _poll;
  bool _disposed = false;
  bool _refreshing = false;
  bool _pollError = false;

  Future<void> connect() async {
    if (_disposed) return;
    loading = true;
    error = null;
    notifyListeners();
    try {
      snapshot = await _api.fetchSnapshot();
      error = null;
      notifyListeners();
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
      if (_pollError ||
          error?.startsWith('Athena service is unavailable') == true) {
        error = null;
      }
      _pollError = false;
      if (!_disposed) notifyListeners();
    } catch (caught) {
      _pollError = true;
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
  Future<void> connectTcp(String host, int port) =>
      _operate(() => _api.connectTcp(host, port));
  Future<void> disconnectBench() => _operate(_api.disconnectBench);
  Future<void> setPulse(int channel, int widthUs) =>
      _operate(() => _api.setPulse(channel, widthUs));
  Future<void> syncTime() => _operate(_api.syncTime);
  Future<void> clearSimulatorCounters() =>
      _operate(_api.clearSimulatorCounters);
  Future<void> uploadProfile(String id) =>
      _operate(() => _api.uploadProfile(id));
  Future<void> control(String action, {int cycles = 1}) =>
      _operate(() => _api.control(action, cycles: cycles));

  Future<void> loadHistory({String? fromDate, String? throughDate}) async {
    if (_disposed || historyLoading) return;
    if (fromDate != null || throughDate != null) {
      historyFromDate = fromDate;
      historyThroughDate = throughDate;
    }
    historyLoading = true;
    historyError = null;
    notifyListeners();
    try {
      final result = await Future.wait([
        _api.historySessions(historyFromDate, historyThroughDate),
        _api.historyEvents(historyFromDate, historyThroughDate),
      ]);
      historySessions = result[0];
      historyEvents = result[1];
    } catch (caught) {
      historySessions = const [];
      historyEvents = const [];
      historyError = caught.toString().replaceFirst(
        RegExp(r'^(Bad state|Exception): '),
        '',
      );
    } finally {
      historyLoading = false;
      if (!_disposed) notifyListeners();
    }
  }

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

  void _scheduleRetry() {
    if (_disposed || _retry?.isActive == true) return;
    _retry = Timer(const Duration(seconds: 3), connect);
  }

  @override
  void dispose() {
    _disposed = true;
    _retry?.cancel();
    _poll?.cancel();
    _api.close();
    super.dispose();
  }
}
