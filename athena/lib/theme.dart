import 'package:flutter/material.dart';

class Palette {
  static const background = Color.fromRGBO(0, 0, 0, 0);
  static const card = Color.fromRGBO(0, 0, 0, 1);
  static const ink = Color.fromRGBO(247, 243, 243, 1);
  static const secondary = Color.fromRGBO(255, 255, 255, 1);
  static const muted = Color.fromRGBO(224, 220, 107, 1);
  static const line = Color.fromRGBO(255, 204, 0, 1);
  static const brand = Color.fromRGBO(200, 48, 46, 1);
  static const good = Color.fromRGBO(12, 163, 12, 1);
  static const critical = Color.fromRGBO(208, 59, 59, 1);

  static const series = [
    Color.fromRGBO(42, 120, 214, 1),
    Color.fromRGBO(235, 104, 52, 1),
    Color.fromRGBO(27, 175, 122, 1),
    Color.fromRGBO(141, 99, 189, 1),
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
      borderRadius: BorderRadius.circular(0),
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
