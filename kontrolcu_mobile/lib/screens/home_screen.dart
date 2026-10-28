import 'package:flutter/material.dart';
import '../services/socket_service.dart';
import 'connect_screen.dart';
import 'tabs/mouse_tab.dart';
import 'tabs/gamepad_tab.dart';
import 'tabs/keyboard_tab.dart';

import 'package:flutter/services.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({Key? key}) : super(key: key);

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _currentIndex = 0;

  final List<Widget> _tabs = [
    const MouseTab(),
    const GamepadTab(),
    const KeyboardTab(),
  ];

  @override
  void initState() {
    super.initState();
    SystemChrome.setPreferredOrientations([
      DeviceOrientation.portraitUp,
    ]);
  }

  @override
  void dispose() {
    SystemChrome.setPreferredOrientations([
      DeviceOrientation.portraitUp,
    ]);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0F1117),
      appBar: AppBar(
        backgroundColor: const Color(0xFF161D2E),
        elevation: 0,
        title: Row(
          children: [
            ValueListenableBuilder<bool>(
              valueListenable: SocketService.instance.isConnected,
              builder: (context, connected, child) {
                return Container(
                  width: 9,
                  height: 9,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: connected ? const Color(0xFF34D399) : const Color(0xFFF87171),
                    boxShadow: connected
                        ? [
                            BoxShadow(
                              color: const Color(0xFF34D399).withOpacity(0.5),
                              blurRadius: 8,
                              spreadRadius: 2,
                            )
                          ]
                        : [],
                  ),
                );
              },
            ),
            const SizedBox(width: 10),
            ValueListenableBuilder<bool>(
              valueListenable: SocketService.instance.isConnected,
              builder: (context, connected, child) {
                return Text(
                  connected ? 'Bağlandı ✓' : 'Bağlantı Kesildi',
                  style: const TextStyle(
                    color: Color(0xFF4B5A72),
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                  ),
                );
              },
            ),
          ],
        ),
        actions: [
          // Hand Mode Toggle Button
          ValueListenableBuilder<bool>(
            valueListenable: SocketService.instance.handModeActive,
            builder: (context, handModeActive, child) {
              return IconButton(
                icon: Icon(
                  handModeActive ? Icons.back_hand : Icons.back_hand_outlined,
                  color: handModeActive ? const Color(0xFFA78BFA) : const Color(0xFF4B5A72),
                ),
                tooltip: 'El Modu (Kamera Kontrolü)',
                onPressed: () {
                  final newValue = !handModeActive;
                  SocketService.instance.sendHandModeToggle(newValue);
                  SocketService.instance.handModeActive.value = newValue;
                  HapticFeedback.lightImpact();
                  ScaffoldMessenger.of(context).hideCurrentSnackBar();
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text(newValue ? 'El Modu Aktif Edildi' : 'El Modu Kapatıldı'),
                      duration: const Duration(seconds: 1),
                      backgroundColor: const Color(0xFF161D2E),
                    ),
                  );
                },
              );
            },
          ),
          // Disconnect button
          IconButton(
            icon: const Icon(Icons.power_settings_new, color: Color(0xFFF87171)),
            onPressed: () {
              SocketService.instance.disconnect();
              Navigator.pushReplacement(
                context,
                MaterialPageRoute(builder: (context) => const ConnectScreen()),
              );
            },
          ),
        ],
      ),
      body: IndexedStack(
        index: _currentIndex,
        children: _tabs,
      ),
      bottomNavigationBar: Container(
        decoration: const BoxDecoration(
          border: Border(
            top: BorderSide(color: Color(0xFF253350), width: 1),
          ),
        ),
        child: BottomNavigationBar(
          currentIndex: _currentIndex,
          onTap: (index) {
            setState(() {
              _currentIndex = index;
            });
            if (index == 1) {
              SystemChrome.setPreferredOrientations([
                DeviceOrientation.landscapeLeft,
                DeviceOrientation.landscapeRight,
              ]);
            } else {
              SystemChrome.setPreferredOrientations([
                DeviceOrientation.portraitUp,
              ]);
            }
          },
          backgroundColor: const Color(0xFF161D2E),
          selectedItemColor: const Color(0xFFA78BFA),
          unselectedItemColor: const Color(0xFF4B5A72),
          selectedFontSize: 11,
          unselectedFontSize: 11,
          type: BottomNavigationBarType.fixed,
          items: const [
            BottomNavigationBarItem(
              icon: Icon(Icons.mouse, size: 20),
              label: 'MOUSE',
            ),
            BottomNavigationBarItem(
              icon: Icon(Icons.gamepad, size: 20),
              label: 'GAMEPAD',
            ),
            BottomNavigationBarItem(
              icon: Icon(Icons.keyboard, size: 20),
              label: 'KLAVYE',
            ),
          ],
        ),
      ),
    );
  }
}
