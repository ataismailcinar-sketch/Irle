import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class JoystickWidget extends StatefulWidget {
  final String label;
  final Function(double x, double y) onChange;
  final VoidCallback onRelease;

  const JoystickWidget({
    Key? key,
    required this.label,
    required this.onChange,
    required this.onRelease,
  }) : super(key: key);

  @override
  State<JoystickWidget> createState() => _JoystickWidgetState();
}

class _JoystickWidgetState extends State<JoystickWidget> {
  Offset _dragPosition = Offset.zero;
  final double _maxRadius = 38.0;

  void _updatePosition(Offset localPos) {
    // Center of the joystick pad is (45, 45) since width/height is 90
    final center = const Offset(45.0, 45.0);
    final offset = localPos - center;
    
    double distance = offset.distance;
    Offset normalized = offset;
    if (distance > 0) {
      normalized = offset / distance;
    }

    if (distance > _maxRadius) {
      _dragPosition = normalized * _maxRadius;
      distance = _maxRadius;
    } else {
      _dragPosition = offset;
    }

    // Emit normalized coordinates (-1.0 to 1.0)
    widget.onChange(_dragPosition.dx / _maxRadius, _dragPosition.dy / _maxRadius);
    setState(() {});
  }

  void _resetPosition() {
    _dragPosition = Offset.zero;
    widget.onRelease();
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        GestureDetector(
          onPanStart: (details) {
            HapticFeedback.lightImpact();
            _updatePosition(details.localPosition);
          },
          onPanUpdate: (details) => _updatePosition(details.localPosition),
          onPanEnd: (_) => _resetPosition(),
          child: Container(
            width: 96,
            height: 96,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: const Color(0xFF1C2535),
              border: Border.all(color: const Color(0xFF253350), width: 2),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withOpacity(0.3),
                  blurRadius: 8,
                  offset: const Offset(0, 4),
                )
              ],
            ),
            child: Stack(
              clipBehavior: Clip.none,
              children: [
                // Center knob background guide
                Center(
                  child: Container(
                    width: 8,
                    height: 8,
                    decoration: const BoxDecoration(
                      shape: BoxShape.circle,
                      color: Color(0xFF253350),
                    ),
                  ),
                ),
                // Movable thumb knob
                Positioned(
                  left: 48.0 - 19.0 + _dragPosition.dx,
                  top: 48.0 - 19.0 + _dragPosition.dy,
                  child: Container(
                    width: 38,
                    height: 38,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      gradient: const LinearGradient(
                        colors: [Color(0xFF6366F1), Color(0xFF312E81)],
                        begin: Alignment.topLeft,
                        end: Alignment.bottomRight,
                      ),
                      boxShadow: [
                        BoxShadow(
                          color: const Color(0xFF6366F1).withOpacity(0.4),
                          blurRadius: 6,
                          offset: const Offset(0, 2),
                        )
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 6),
        Text(
          widget.label,
          style: const TextStyle(
            color: Color(0xFF4B5A72),
            fontSize: 9,
            fontWeight: FontWeight.w800,
            letterSpacing: 0.8,
          ),
        ),
      ],
    );
  }
}
