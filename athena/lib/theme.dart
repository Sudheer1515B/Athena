import 'package:flutter/material.dart';

class Palette {
  static const background = Color(0xFFF4F4F2);
  static const card = Colors.white;
  static const ink = Color(0xFF0B0B0B);
  static const secondary = Color(0xFF52514E);
  static const muted = Color(0xFF8A8985);
  static const line = Color(0xFFE3E2DE);
  static const brand = Color(0xFFC8302E);
  static const good = Color(0xFF0CA30C);
  static const critical = Color(0xFFD03B3B);
  static const series = [
    Color(0xFF2A78D6),
    Color(0xFFEB6834),
    Color(0xFF1BAF7A),
    Color(0xFF8D63BD),
  ];
}

class HeaderLabel extends StatelessWidget {
  const HeaderLabel(this.text, {super.key});
  final String text;
  @override
  Widget build(BuildContext context) => Text(
    text,
    style: const TextStyle(
      color: Palette.secondary,
      fontSize: 12,
      fontWeight: FontWeight.w600,
      letterSpacing: .4,
    ),
  );
}

class BenchCard extends StatelessWidget {
  const BenchCard({super.key, this.title, required this.child});
  final String? title;
  final Widget child;

  @override
  Widget build(BuildContext context) => Container(
    width: double.infinity,
    padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 16),
    decoration: BoxDecoration(
      color: Palette.card,
      border: Border.all(color: Palette.line),
      borderRadius: BorderRadius.circular(10),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (title != null) ...[
          Text(
            title!.toUpperCase(),
            style: const TextStyle(
              color: Palette.secondary,
              fontSize: 13,
              fontWeight: FontWeight.w600,
              letterSpacing: 1,
            ),
          ),
          const SizedBox(height: 12),
        ],
        child,
      ],
    ),
  );
}
