import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../../services/socket_service.dart';

class KeyboardTab extends StatefulWidget {
  const KeyboardTab({Key? key}) : super(key: key);

  @override
  State<KeyboardTab> createState() => _KeyboardTabState();
}

class _KeyboardTabState extends State<KeyboardTab> {
  final TextEditingController _typeController = TextEditingController();
  final FocusNode _focusNode = FocusNode();
  String _previousValue = '';
  
  bool _shiftActive = false;
  bool _ctrlActive = false;

  @override
  void initState() {
    super.initState();
    _typeController.addListener(_onTypeChanged);
  }

  @override
  void dispose() {
    _typeController.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  void _onTypeChanged() {
    final value = _typeController.text;
    if (value == _previousValue) return;

    if (value.length > _previousValue.length) {
      // Characters typed
      final added = value.substring(_previousValue.length);
      for (int i = 0; i < added.length; i++) {
        final char = added[i];
        final keyToSend = char == ' ' ? 'space' : char;
        _sendKey(keyToSend);
      }
    } else if (value.length < _previousValue.length) {
      // Backspace typed
      final diff = _previousValue.length - value.length;
      for (int i = 0; i < diff; i++) {
        _sendKey('backspace');
      }
    }

    _previousValue = value;
  }

  void _sendKey(String key) {
    HapticFeedback.lightImpact();
    List<String> mods = [];
    if (_shiftActive) {
      mods.add('shift');
      setState(() => _shiftActive = false);
    }
    if (_ctrlActive) {
      mods.add('ctrl');
      setState(() => _ctrlActive = false);
    }
    SocketService.instance.sendKeyPress(key, mods);
  }

  void _sendHotkey(List<String> keys) {
    HapticFeedback.lightImpact();
    SocketService.instance.sendHotkey(keys);
  }

  Widget _buildQuickKey(String label, String keyVal, {int flex = 1, Color? color}) {
    return Expanded(
      flex: flex,
      child: Padding(
        padding: const EdgeInsets.all(3.0),
        child: ElevatedButton(
          onPressed: () => _sendKey(keyVal),
          style: ElevatedButton.styleFrom(
            backgroundColor: color ?? const Color(0xFF1C2535),
            foregroundColor: const Color(0xFFE2E8F0),
            padding: const EdgeInsets.symmetric(vertical: 12),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(8),
              side: const BorderSide(color: Color(0xFF253350)),
            ),
            elevation: 0,
          ),
          child: Text(
            label,
            style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
          ),
        ),
      ),
    );
  }

  Widget _buildHotkeyButton(String label, List<String> keys) {
    return Padding(
      padding: const EdgeInsets.all(3.0),
      child: ElevatedButton(
        onPressed: () => _sendHotkey(keys),
        style: ElevatedButton.styleFrom(
          backgroundColor: const Color(0xFF1C2535),
          foregroundColor: const Color(0xFFE2E8F0),
          padding: const EdgeInsets.symmetric(vertical: 10),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(8),
            side: const BorderSide(color: Color(0xFF253350)),
          ),
          elevation: 0,
        ),
        child: Text(
          label,
          style: const TextStyle(fontSize: 10, fontWeight: FontWeight.w700),
          textAlign: TextAlign.center,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () {
        // Dismiss keyboard when tapping empty space
        _focusNode.unfocus();
      },
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(12.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Native Keyboard Input Button
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: const Color(0xFF161D2E),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: const Color(0xFF253350)),
              ),
              child: Column(
                children: [
                  TextField(
                    focusNode: _focusNode,
                    controller: _typeController,
                    autocorrect: false,
                    enableSuggestions: false,
                    style: const TextStyle(color: Colors.transparent, fontSize: 1), // Hide real text input visually
                    cursorColor: Colors.transparent,
                    decoration: InputDecoration(
                      border: InputBorder.none,
                      isDense: true,
                      contentPadding: EdgeInsets.zero,
                      prefixIcon: ElevatedButton.icon(
                        onPressed: () {
                          if (_focusNode.hasFocus) {
                            _focusNode.unfocus();
                          } else {
                            _focusNode.requestFocus();
                          }
                        },
                        icon: const Icon(Icons.keyboard_alt),
                        label: Text(_focusNode.hasFocus ? 'Klavyeyi Kapat' : 'Yazmak için Dokunun...'),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: const Color(0xFF6366F1),
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                          elevation: 0,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            
            // Modifier row
            Row(
              children: [
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 3.0),
                    child: ElevatedButton(
                      onPressed: () {
                        setState(() {
                          _shiftActive = !_shiftActive;
                        });
                      },
                      style: ElevatedButton.styleFrom(
                        backgroundColor: _shiftActive ? const Color(0xFFA78BFA) : const Color(0xFF1C2535),
                        foregroundColor: _shiftActive ? Colors.black : const Color(0xFFE2E8F0),
                        padding: const EdgeInsets.symmetric(vertical: 12),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(8),
                          side: const BorderSide(color: Color(0xFF253350)),
                        ),
                        elevation: 0,
                      ),
                      child: const Text('⇧ Shift', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700)),
                    ),
                  ),
                ),
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 3.0),
                    child: ElevatedButton(
                      onPressed: () {
                        setState(() {
                          _ctrlActive = !_ctrlActive;
                        });
                      },
                      style: ElevatedButton.styleFrom(
                        backgroundColor: _ctrlActive ? const Color(0xFFA78BFA) : const Color(0xFF1C2535),
                        foregroundColor: _ctrlActive ? Colors.black : const Color(0xFFE2E8F0),
                        padding: const EdgeInsets.symmetric(vertical: 12),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(8),
                          side: const BorderSide(color: Color(0xFF253350)),
                        ),
                        elevation: 0,
                      ),
                      child: const Text('Ctrl', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700)),
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),

            // D-Pad Row / navigation
            Row(
              children: [
                _buildQuickKey('Esc', 'escape', color: const Color(0xFF253350)),
                _buildQuickKey('Tab', 'tab'),
                _buildQuickKey('Del', 'delete'),
                _buildQuickKey('⌫ Sil', 'backspace', flex: 2),
              ],
            ),
            Row(
              children: [
                _buildQuickKey('Win', 'win'),
                _buildQuickKey('Alt', 'alt'),
                _buildQuickKey('BOŞLUK', 'space', flex: 3, color: const Color(0xFF161D2E)),
                _buildQuickKey('↵ Enter', 'enter', flex: 2, color: const Color(0xFF6366F1)),
              ],
            ),

            const SizedBox(height: 12),
            const Text(
              'YÖN TUŞLARI',
              style: TextStyle(color: Color(0xFF4B5A72), fontSize: 9, fontWeight: FontWeight.w800, letterSpacing: 1),
            ),
            const SizedBox(height: 4),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Spacer(),
                _buildQuickKey('▲', 'up'),
                const Spacer(),
              ],
            ),
            Row(
              children: [
                const Spacer(),
                _buildQuickKey('◀', 'left'),
                _buildQuickKey('▼', 'down'),
                _buildQuickKey('▶', 'right'),
                const Spacer(),
              ],
            ),

            const SizedBox(height: 16),
            const Text(
              'KLAVYE KISAYOLLARI',
              style: TextStyle(color: Color(0xFF4B5A72), fontSize: 9, fontWeight: FontWeight.w800, letterSpacing: 1),
            ),
            const SizedBox(height: 6),
            GridView.count(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              crossAxisCount: 3,
              childAspectRatio: 1.8,
              children: [
                _buildHotkeyButton('Kopyala\n(Ctrl+C)', ['ctrl', 'c']),
                _buildHotkeyButton('Yapıştır\n(Ctrl+V)', ['ctrl', 'v']),
                _buildHotkeyButton('Geri Al\n(Ctrl+Z)', ['ctrl', 'z']),
                _buildHotkeyButton('Hepsini Seç\n(Ctrl+A)', ['ctrl', 'a']),
                _buildHotkeyButton('Pencere Değiş\n(Alt+Tab)', ['alt', 'tab']),
                _buildHotkeyButton('Masaüstü\n(Win+D)', ['win', 'd']),
                _buildHotkeyButton('Kapat\n(Ctrl+W)', ['ctrl', 'w']),
                _buildHotkeyButton('Kilitle\n(Win+L)', ['win', 'l']),
                _buildHotkeyButton('Taskmgr\n(C+S+Esc)', ['ctrl', 'shift', 'escape']),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
