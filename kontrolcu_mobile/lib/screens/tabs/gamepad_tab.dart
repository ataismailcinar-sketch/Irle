import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../../services/socket_service.dart';
import '../../widgets/joystick_widget.dart';
import '../../widgets/dpad_widget.dart';

class GamepadTab extends StatefulWidget {
  const GamepadTab({Key? key}) : super(key: key);

  @override
  State<GamepadTab> createState() => _GamepadTabState();
}

class _HomeScreenState extends State<GamepadTab> {
  @override
  Widget build(BuildContext context) {
    return Container();
  }
}

class _GamepadTabState extends State<GamepadTab> {
  // Helper for D-pad/Action/System buttons that send down/up states
  Widget _buildButton({
    required String btnKey,
    required String label,
    required Color color,
    double width = 50.0,
    double height = 50.0,
    bool isCircle = false,
    Color textColor = Colors.white,
  }) {
    return GestureDetector(
      onTapDown: (_) {
        HapticFeedback.lightImpact();
        SocketService.instance.sendGamepadButton(btnKey, 'd');
      },
      onTapUp: (_) => SocketService.instance.sendGamepadButton(btnKey, 'u'),
      onTapCancel: () => SocketService.instance.sendGamepadButton(btnKey, 'u'),
      child: Container(
        width: width,
        height: height,
        decoration: BoxDecoration(
          shape: isCircle ? BoxShape.circle : BoxShape.rectangle,
          borderRadius: isCircle ? null : BorderRadius.circular(12),
          color: color,
          border: Border.all(color: const Color(0xFF253350), width: 1),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.2),
              blurRadius: 4,
              offset: const Offset(0, 2),
            )
          ],
        ),
        child: Center(
          child: Text(
            label,
            style: TextStyle(
              color: textColor,
              fontWeight: FontWeight.w800,
              fontSize: 13,
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildTriggerButton({required String btnKey, required String label}) {
    return _buildButton(
      btnKey: btnKey,
      label: label,
      color: const Color(0xFF1C2535),
      width: double.infinity,
      height: 44,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 10.0, vertical: 6.0),
      child: Row(
        children: [
          // --- LEFT SIDE CONTROLS ---
          Expanded(
            flex: 4,
            child: Column(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: [
                // LT / LB shoulder row
                Row(
                  children: [
                    Expanded(child: _buildTriggerButton(btnKey: 'lt', label: '◀ LT')),
                    const SizedBox(width: 8),
                    Expanded(child: _buildTriggerButton(btnKey: 'lb', label: 'LB')),
                  ],
                ),
                // Sol stick & Dpad side-by-side
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                  children: [
                    JoystickWidget(
                      label: 'SOL STICK',
                      onChange: (x, y) => SocketService.instance.sendStick('left', x, y),
                      onRelease: () => SocketService.instance.sendStick('left', 0.0, 0.0),
                    ),
                    const DpadWidget(),
                  ],
                ),
              ],
            ),
          ),
          
          const SizedBox(width: 12),

          // --- CENTER SYSTEM CONTROLS ---
          Expanded(
            flex: 2,
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                _buildButton(
                  btnKey: 'home',
                  label: '⬡',
                  color: const Color(0xFF1C2535),
                  width: 44,
                  height: 44,
                  isCircle: true,
                  textColor: const Color(0xFFA78BFA),
                ),
                const SizedBox(height: 12),
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    _buildButton(
                      btnKey: 'back',
                      label: '◀',
                      color: const Color(0xFF161D2E),
                      width: 38,
                      height: 28,
                    ),
                    const SizedBox(width: 8),
                    _buildButton(
                      btnKey: 'start',
                      label: '▶',
                      color: const Color(0xFF161D2E),
                      width: 38,
                      height: 28,
                    ),
                  ],
                ),
              ],
            ),
          ),

          const SizedBox(width: 12),

          // --- RIGHT SIDE CONTROLS ---
          Expanded(
            flex: 4,
            child: Column(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: [
                // RB / RT shoulder row
                Row(
                  children: [
                    Expanded(child: _buildTriggerButton(btnKey: 'rb', label: 'RB')),
                    const SizedBox(width: 8),
                    Expanded(child: _buildTriggerButton(btnKey: 'rt', label: 'RT ▶')),
                  ],
                ),
                // Sağ stick & ABXY face buttons side-by-side
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                  children: [
                    JoystickWidget(
                      label: 'SAG STICK',
                      onChange: (x, y) => SocketService.instance.sendStick('right', x, y),
                      onRelease: () => SocketService.instance.sendStick('right', 0.0, 0.0),
                    ),
                    // ABXY Face buttons
                    Container(
                      width: 100,
                      height: 100,
                      child: Stack(
                        children: [
                          // Y (Top)
                          Positioned(
                            top: 0,
                            left: 33,
                            child: _buildButton(
                              btnKey: 'y',
                              label: 'Y',
                              color: const Color(0xFFF59E0B),
                              isCircle: true,
                              width: 34,
                              height: 34,
                              textColor: Colors.black,
                            ),
                          ),
                          // B (Right)
                          Positioned(
                            top: 33,
                            right: 0,
                            child: _buildButton(
                              btnKey: 'b',
                              label: 'B',
                              color: const Color(0xFFF87171),
                              isCircle: true,
                              width: 34,
                              height: 34,
                            ),
                          ),
                          // A (Bottom)
                          Positioned(
                            bottom: 0,
                            left: 33,
                            child: _buildButton(
                              btnKey: 'a',
                              label: 'A',
                              color: const Color(0xFF34D399),
                              isCircle: true,
                              width: 34,
                              height: 34,
                              textColor: Colors.black,
                            ),
                          ),
                          // X (Left)
                          Positioned(
                            top: 33,
                            left: 0,
                            child: _buildButton(
                              btnKey: 'x',
                              label: 'X',
                              color: const Color(0xFF60A5FA),
                              isCircle: true,
                              width: 34,
                              height: 34,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
