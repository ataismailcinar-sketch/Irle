import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../services/socket_service.dart';

class DpadWidget extends StatefulWidget {
  const DpadWidget({Key? key}) : super(key: key);

  @override
  State<DpadWidget> createState() => _DpadWidgetState();
}

class _DpadWidgetState extends State<DpadWidget> {
  final Map<String, bool> _activeKeys = {
    'up': false,
    'down': false,
    'left': false,
    'right': false,
  };

  void _sendState(String dir, String state) {
    HapticFeedback.lightImpact();
    SocketService.instance.sendDpad(dir, state);
    setState(() {
      _activeKeys[dir] = (state == 'd');
    });
  }

  Widget _buildDpadButton({
    required String dir,
    required IconData icon,
    required double? top,
    required double? bottom,
    required double? left,
    required double? right,
  }) {
    final active = _activeKeys[dir] ?? false;
    return Positioned(
      top: top,
      bottom: bottom,
      left: left,
      right: right,
      child: GestureDetector(
        onTapDown: (_) => _sendState(dir, 'd'),
        onTapUp: (_) => _sendState(dir, 'u'),
        onTapCancel: () => _sendState(dir, 'u'),
        child: Container(
          width: 36,
          height: 36,
          decoration: BoxDecoration(
            color: active ? const Color(0xFF6366F1) : const Color(0xFF1C2535),
            borderRadius: BorderRadius.circular(6),
            border: Border.all(
              color: active ? const Color(0xFF6366F1) : const Color(0xFF253350),
              width: 1,
            ),
          ),
          child: Icon(
            icon,
            color: active ? Colors.white : const Color(0xFFE2E8F0),
            size: 18,
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 108,
      height: 108,
      child: Stack(
        children: [
          // Center core connection
          Center(
            child: Container(
              width: 38,
              height: 38,
              decoration: const BoxDecoration(
                shape: BoxShape.circle,
                color: Color(0xFF253350),
              ),
            ),
          ),
          // Up
          _buildDpadButton(
            dir: 'up',
            icon: Icons.arrow_drop_up,
            top: 0,
            bottom: null,
            left: 36,
            right: null,
          ),
          // Down
          _buildDpadButton(
            dir: 'down',
            icon: Icons.arrow_drop_down,
            top: 72,
            bottom: null,
            left: 36,
            right: null,
          ),
          // Left
          _buildDpadButton(
            dir: 'left',
            icon: Icons.arrow_left,
            top: 36,
            bottom: null,
            left: 0,
            right: null,
          ),
          // Right
          _buildDpadButton(
            dir: 'right',
            icon: Icons.arrow_right,
            top: 36,
            bottom: null,
            left: 72,
            right: null,
          ),
        ],
      ),
    );
  }
}
