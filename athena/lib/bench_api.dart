import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;
import 'package:web_socket_channel/web_socket_channel.dart';

class BenchSnapshot {
  const BenchSnapshot({
    required this.connectionState,
    required this.observedAt,
    required this.historyCounts,
    required this.connection,
    required this.benchState,
    required this.counters,
    required this.profile,
    required this.recentEvents,
  });

  final String connectionState;
  final DateTime? observedAt;
  final Map<String, int> historyCounts;
  final Map<String, dynamic> connection;
  final Map<String, dynamic>? benchState;
  final Map<String, dynamic>? counters;
  final Map<String, dynamic>? profile;
  final List<String> recentEvents;

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
      connection: connection is Map
          ? Map<String, dynamic>.from(connection)
          : const {},
      benchState: json['bench_state'] is Map
          ? Map<String, dynamic>.from(json['bench_state'] as Map)
          : null,
      counters: json['counters'] is Map
          ? Map<String, dynamic>.from(json['counters'] as Map)
          : null,
      profile: json['profile'] is Map
          ? Map<String, dynamic>.from(json['profile'] as Map)
          : null,
      recentEvents: (json['recent_events'] as List? ?? const [])
          .map((event) => event.toString())
          .toList(),
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
    return BenchSnapshot.fromJson(_decodeObject(response));
  }

  Future<Map<String, dynamic>> importSource(
    String filename,
    Uint8List bytes,
  ) async {
    final request = http.MultipartRequest('POST', endpoint('sources'));
    request.files.add(
      http.MultipartFile.fromBytes('file', bytes, filename: filename),
    );
    final response = await http.Response.fromStream(
      await _client.send(request),
    );
    return _decodeObject(response);
  }

  Future<Map<String, dynamic>> compileProfile(
    Map<String, dynamic> settings,
  ) async {
    final response = await _client.post(
      endpoint('profiles'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(settings),
    );
    return _decodeObject(response);
  }

  Future<Map<String, dynamic>> sourcePreview(
    String sourceId,
    List<String> channels,
    int startUs,
    int endUs,
  ) async {
    final uri = endpoint('sources/$sourceId/preview').replace(
      queryParameters: {
        'channels': channels.join(','),
        'start_us': '$startUs',
        'end_us': '$endUs',
        'max_points': '1000',
      },
    );
    return _decodeObject(await _client.get(uri));
  }

  Future<Map<String, dynamic>> profilePreview(String profileId) async =>
      _decodeObject(await _client.get(endpoint('profiles/$profileId/preview')));

  Future<Map<String, dynamic>> recentSources() async =>
      _decodeObject(await _client.get(endpoint('sources')));

  Future<Map<String, dynamic>> recentProfiles() async =>
      _decodeObject(await _client.get(endpoint('profiles')));

  Future<BenchSnapshot> connectUsb(String port) async => BenchSnapshot.fromJson(
    _decodeObject(
      await _client.post(
        endpoint('bench/usb/connect'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'port': port}),
      ),
    ),
  );

  Future<BenchSnapshot> disconnectUsb() async => BenchSnapshot.fromJson(
    _decodeObject(await _client.post(endpoint('bench/usb/disconnect'))),
  );

  Future<BenchSnapshot> uploadProfile(String profileId) async =>
      BenchSnapshot.fromJson(
        _decodeObject(await _client.post(endpoint('bench/upload/$profileId'))),
      );

  Future<BenchSnapshot> control(String action, {int cycles = 1}) async =>
      BenchSnapshot.fromJson(
        _decodeObject(
          await _client.post(
            endpoint('bench/$action'),
            headers: {'Content-Type': 'application/json'},
            body: action == 'start' ? jsonEncode({'cycles': cycles}) : null,
          ),
        ),
      );

  Uri profileExportUri(String profileId) =>
      endpoint('profiles/$profileId/export.csv');

  Map<String, dynamic> _decodeObject(http.Response response) {
    Map<String, dynamic> body;
    try {
      body = jsonDecode(response.body) as Map<String, dynamic>;
    } catch (_) {
      throw StateError('The Athena service returned an invalid response.');
    }
    if (response.statusCode >= 400) {
      final detail = body['detail'];
      if (detail is Map && detail['message'] != null) {
        throw StateError(detail['message'].toString());
      }
      throw StateError(
        detail?.toString() ?? 'Request failed (${response.statusCode}).',
      );
    }
    return body;
  }

  WebSocketChannel openLive() {
    final httpUri = endpoint('live');
    return WebSocketChannel.connect(
      httpUri.replace(scheme: httpUri.scheme == 'https' ? 'wss' : 'ws'),
    );
  }

  void close() => _client.close();
}
