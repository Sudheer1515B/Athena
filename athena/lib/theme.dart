import 'package:flutter/material.dart';

class Palette {
  static const background = Color(0xFF050505);
  static const card = Color(0xFF101010);
  static const ink = Color(0xFFF6F6F2);
  static const secondary = Color(0xFFE3E3DE);
  static const muted = Color(0xFFA1A19A);
  static const line = Color(0xFF3D3D38);
  static const brand = Color(0xFFF3E64D);
  static const good = Color(0xFF7ADBA2);
  static const critical = Color(0xFFFF7777);

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
              fontWeight: FontWeight.w700,
              letterSpacing: 1.5,
            ),
          ),
          const SizedBox(height: 12),
        ],
        child,
      ],
    ),
  );
}

/// A read-only dashboard tile with a bottom-up inverse-color reveal on hover.
class HoverMetricTile extends StatefulWidget {
  const HoverMetricTile({
    super.key,
    required this.label,
    required this.value,
    required this.detail,
  });

  final String label;
  final String value;
  final String detail;

  @override
  State<HoverMetricTile> createState() => _HoverMetricTileState();
}

class _HoverMetricTileState extends State<HoverMetricTile> {
  bool hovered = false;

  Widget _content({required bool inverted}) {
    final foreground = inverted ? Palette.background : Palette.ink;
    final subtle = inverted ? Palette.background : Palette.muted;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 19),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            widget.label.toUpperCase(),
            style: TextStyle(
              color: foreground,
              fontSize: 11,
              fontWeight: FontWeight.w700,
              letterSpacing: 1.45,
            ),
          ),
          const SizedBox(height: 13),
          Text(
            widget.value,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: foreground,
              fontSize: 30,
              height: 1.1,
              fontWeight: FontWeight.w800,
              letterSpacing: -.8,
            ),
          ),
          const SizedBox(height: 10),
          Text(
            widget.detail,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(color: subtle, fontSize: 12),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) => MouseRegion(
    onEnter: (_) => setState(() => hovered = true),
    onExit: (_) => setState(() => hovered = false),
    child: TweenAnimationBuilder<double>(
      tween: Tween(end: hovered ? 1 : 0),
      duration: const Duration(milliseconds: 280),
      curve: Curves.easeOutCubic,
      builder: (context, reveal, _) => Container(
        width: double.infinity,
        decoration: BoxDecoration(
          color: Palette.card,
          border: Border.all(color: hovered ? Palette.ink : Palette.line),
        ),
        child: Stack(
          children: [
            _content(inverted: false),
            Positioned.fill(
              child: ClipRect(
                clipper: _BottomRevealClipper(reveal),
                child: ColoredBox(
                  color: Palette.ink,
                  child: ExcludeSemantics(child: _content(inverted: true)),
                ),
              ),
            ),
          ],
        ),
      ),
    ),
  );
}

class _BottomRevealClipper extends CustomClipper<Rect> {
  const _BottomRevealClipper(this.progress);

  final double progress;

  @override
  Rect getClip(Size size) => Rect.fromLTWH(
    0,
    size.height * (1 - progress),
    size.width,
    size.height * progress,
  );

  @override
  bool shouldReclip(_BottomRevealClipper oldClipper) =>
      oldClipper.progress != progress;
}
