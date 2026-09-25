import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:web_socket_channel/web_socket_channel.dart';

class BenchSnapshot {
  const BenchSnapshot({
    required this.connectionState,
    required this.observedAt,
    required this.historyCounts,
  });

  final String connectionState;
  final DateTime? observedAt;
  final Map<String, int> historyCounts;

  factory BenchSnapshot.fromJson(Map<String, dynamic> json) {
    final connection = json['connection'];
    final rawCounts = json['history_counts'];
    return BenchSnapshot(
      connectionState: connection is Map
          ? (connection['state']?.toString() ?? 'UNKNOWN')
          : 'UNKNOWN',
      observedAt: DateTime.tryParse(json['observed_at']?.toString() ?? ''),
      historyCounts: rawCounts is Map
          ? rawCounts.map(
              (key, value) => MapEntry(key.toString(), (value as num).toInt()),
            )
          : const {},
    );
  }
}

class BenchApi {
  BenchApi({http.Client? client}) : _client = client ?? http.Client();

  static const configuredBase = String.fromEnvironment('ATHENA_API_BASE');
  final http.Client _client;

  Uri get baseUri => configuredBase.isEmpty
      ? Uri.base
      : Uri.parse(
          configuredBase.endsWith('/') ? configuredBase : '$configuredBase/',
        );

  Uri endpoint(String path) => baseUri.resolve('/api/v1/$path');

  Future<BenchSnapshot> fetchSnapshot() async {
    final response = await _client.get(endpoint('snapshot'));
    if (response.statusCode != 200) {
      throw StateError('Snapshot request failed (${response.statusCode})');
    }
    return BenchSnapshot.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  WebSocketChannel openLive() {
    final httpUri = endpoint('live');
    return WebSocketChannel.connect(
      httpUri.replace(scheme: httpUri.scheme == 'https' ? 'wss' : 'ws'),
    );
  }

  void close() => _client.close();
}
