import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../../services/socket_service.dart';

class MouseTab extends StatefulWidget {
  const MouseTab({Key? key}) : super(key: key);

  @override
  State<MouseTab> createState() => _MouseTabState();
}

class _MouseTabState extends State<MouseTab> {
  double _sensitivity = 4.0;
  
  // Touch tracking state
  double? _lastX;
  double? _lastY;
  double? _lastScrollY;
  double? _startX;
  double? _startY;
  bool _hasMoved = false;
  double _totalDistance = 0.0;
  final Map<int, Offset> _pointers = {};
  int _lastTapTime = 0;

  void _handlePointerDown(PointerDownEvent event) {
    _pointers[event.pointer] = event.position;
    if (_pointers.length == 1) {
      _lastX = event.position.dx;
      _lastY = event.position.dy;
      _startX = event.position.dx;
      _startY = event.position.dy;
      _hasMoved = false;
      _totalDistance = 0.0;
    } else if (_pointers.length == 2) {
      _lastScrollY = event.position.dy;
    }
  }

  void _handlePointerMove(PointerMoveEvent event) {
    _pointers[event.pointer] = event.position;
    
    if (_pointers.length == 1 && _lastX != null && _lastY != null) {
      // Single finger drag = mouse move
      final dx = event.position.dx - _lastX!;
      final dy = event.position.dy - _lastY!;
      
      final scaledDx = dx * _sensitivity * 0.7;
      final scaledDy = dy * _sensitivity * 0.7;
      
      if (scaledDx != 0 || scaledDy != 0) {
        SocketService.instance.sendMouseMove(scaledDx, scaledDy);
      }
      
      // Calculate total movement distance
      if (_startX != null && _startY != null) {
        final dragDistX = event.position.dx - _startX!;
        final dragDistY = event.position.dy - _startY!;
        _totalDistance = dragDistX * dragDistX + dragDistY * dragDistY;
        if (_totalDistance > 49.0) { // Dragged more than 7 logical pixels
          _hasMoved = true;
        }
      }
      
      _lastX = event.position.dx;
      _lastY = event.position.dy;
    } else if (_pointers.length == 2 && _lastScrollY != null) {
      // Two finger drag = scroll
      final currentY = event.position.dy;
      final dy = currentY - _lastScrollY!;
      
      if (dy.abs() > 1.5) {
        final dir = dy < 0 ? 'up' : 'down';
        final amt = dy.abs() * 0.5;
        SocketService.instance.sendScroll(dir, amt);
        _lastScrollY = currentY;
      }
    }
  }

  void _handlePointerUp(PointerEvent event) {
    final wasSingleFinger = _pointers.length == 1;
    _pointers.remove(event.pointer);
    
    if (_pointers.isEmpty) {
      _lastX = null;
      _lastY = null;
      _lastScrollY = null;
      _startX = null;
      _startY = null;
      
      if (wasSingleFinger && !_hasMoved) {
        final now = DateTime.now().millisecondsSinceEpoch;
        if (now - _lastTapTime < 280) {
          HapticFeedback.mediumImpact();
          SocketService.instance.sendMouseClick('double');
        } else {
          HapticFeedback.lightImpact();
          SocketService.instance.sendMouseClick('left');
        }
        _lastTapTime = now;
      }
      _hasMoved = false;
      _totalDistance = 0.0;
    }
  }

  void _handleButtonClick(String button) {
    HapticFeedback.lightImpact();
    SocketService.instance.sendMouseClick(button);
  }

  void _handleScrollClick(String dir) {
    HapticFeedback.lightImpact();
    SocketService.instance.sendScroll(dir, 120.0);
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(12.0),
      child: Column(
        children: [
          // Sensitivity Slider Row
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
            decoration: BoxDecoration(
              color: const Color(0xFF161D2E),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: const Color(0xFF253350)),
            ),
            child: Row(
              children: [
                const Text(
                  '⚡ Hız',
                  style: TextStyle(
                    color: Color(0xFF4B5A72),
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                Expanded(
                  child: Slider(
                    value: _sensitivity,
                    min: 1.0,
                    max: 10.0,
                    divisions: 9,
                    activeColor: const Color(0xFF6366F1),
                    inactiveColor: const Color(0xFF253350),
                    label: _sensitivity.toInt().toString(),
                    onChanged: (val) {
                      setState(() {
                        _sensitivity = val;
                      });
                    },
                  ),
                ),
                Text(
                  _sensitivity.toInt().toString(),
                  style: const TextStyle(
                    color: Color(0xFFA78BFA),
                    fontSize: 12,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          // Large Touchpad
          Expanded(
            child: Listener(
              onPointerDown: _handlePointerDown,
              onPointerMove: _handlePointerMove,
              onPointerUp: _handlePointerUp,
              onPointerCancel: _handlePointerUp,
              child: Container(
                width: double.infinity,
                decoration: BoxDecoration(
                  color: const Color(0xFF1C2535),
                  borderRadius: BorderRadius.circular(18),
                  border: Border.all(color: const Color(0xFF253350), width: 1.5),
                ),
                child: Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(
                        Icons.touch_app,
                        color: const Color(0xFF4B5A72).withOpacity(0.5),
                        size: 32,
                      ),
                      const SizedBox(height: 10),
                      const Text(
                        '☝️ Kaydır → Fare Hareketi\n✌️ 2 Parmak → Scroll\n👆👆 Çift Dokun → Çift Tık',
                        style: TextStyle(
                          color: Color(0xFF4B5A72),
                          fontSize: 11,
                          height: 1.8,
                        ),
                        textAlign: TextAlign.center,
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(height: 12),
          // Mouse Click Buttons
          Row(
            children: [
              Expanded(
                child: ElevatedButton.icon(
                  onPressed: () => _handleButtonClick('left'),
                  icon: const Icon(Icons.mouse, size: 16),
                  label: const Text('Sol Tık'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF1C2535),
                    foregroundColor: const Color(0xFFE2E8F0),
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                      side: const BorderSide(color: Color(0xFF253350)),
                    ),
                    elevation: 0,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: ElevatedButton.icon(
                  onPressed: () => _handleButtonClick('right'),
                  icon: const Icon(Icons.mouse_outlined, size: 16),
                  label: const Text('Sağ Tık'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF1C2535),
                    foregroundColor: const Color(0xFFE2E8F0),
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                      side: const BorderSide(color: Color(0xFF253350)),
                    ),
                    elevation: 0,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          // Scroll Buttons
          Row(
            children: [
              Expanded(
                child: ElevatedButton(
                  onPressed: () => _handleScrollClick('up'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF1C2535),
                    foregroundColor: const Color(0xFFE2E8F0),
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                      side: const BorderSide(color: Color(0xFF253350)),
                    ),
                    elevation: 0,
                  ),
                  child: const Icon(Icons.keyboard_arrow_up),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: ElevatedButton(
                  onPressed: () => _handleButtonClick('middle'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF1C2535),
                    foregroundColor: const Color(0xFFE2E8F0),
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                      side: const BorderSide(color: Color(0xFF253350)),
                    ),
                    elevation: 0,
                  ),
                  child: const Text('Orta Tık', style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold)),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: ElevatedButton(
                  onPressed: () => _handleScrollClick('down'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF1C2535),
                    foregroundColor: const Color(0xFFE2E8F0),
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                      side: const BorderSide(color: Color(0xFF253350)),
                    ),
                    elevation: 0,
                  ),
                  child: const Icon(Icons.keyboard_arrow_down),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
