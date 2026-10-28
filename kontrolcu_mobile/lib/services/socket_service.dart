import 'package:flutter/material.dart';
import 'package:socket_io_client/socket_io_client.dart' as IO;

class SocketService {
  // Singleton pattern
  SocketService._privateConstructor();
  static final SocketService instance = SocketService._privateConstructor();

  IO.Socket? _socket;
  final ValueNotifier<bool> isConnected = ValueNotifier<bool>(false);
  final ValueNotifier<bool> handModeActive = ValueNotifier<bool>(true);
  String? currentUrl;

  void connect(String url, {VoidCallback? onSuccess, Function(dynamic)? onError}) {
    if (_socket != null) {
      _socket!.disconnect();
      _socket!.destroy();
    }

    currentUrl = url;
    // Standard Socket.IO client initialization
    _socket = IO.io(
      url,
      IO.OptionBuilder()
          .setTransports(['websocket'])
          .disableAutoConnect()
          .enableForceNew()
          .build(),
    );

    _socket!.onConnect((_) {
      isConnected.value = true;
      if (onSuccess != null) onSuccess();
    });

    _socket!.onDisconnect((_) {
      isConnected.value = false;
    });

    _socket!.onConnectError((err) {
      isConnected.value = false;
      if (onError != null) onError(err);
    });

    _socket!.on('hand_mode_changed', (data) {
      if (data is Map) {
        handModeActive.value = data['active'] ?? true;
      }
    });

    _socket!.connect();
  }

  void disconnect() {
    if (_socket != null) {
      _socket!.disconnect();
      _socket = null;
      isConnected.value = false;
    }
  }

  // --- Emitters ---

  void sendMouseMove(double dx, double dy) {
    if (isConnected.value && _socket != null) {
      _socket!.emit('mm', {'dx': dx, 'dy': dy});
    }
  }

  void sendMouseClick(String button) {
    if (isConnected.value && _socket != null) {
      _socket!.emit('mc', {'b': button});
    }
  }

  void sendScroll(String direction, double amount) {
    if (isConnected.value && _socket != null) {
      _socket!.emit('scroll', {'dir': direction, 'amt': amount});
    }
  }

  void sendGamepadButton(String button, String state) {
    if (isConnected.value && _socket != null) {
      _socket!.emit('gp', {'btn': button, 'state': state});
    }
  }

  void sendDpad(String direction, String state) {
    if (isConnected.value && _socket != null) {
      _socket!.emit('dp', {'dir': direction, 'state': state});
    }
  }

  void sendStick(String side, double x, double y) {
    if (isConnected.value && _socket != null) {
      _socket!.emit('stick', {'side': side, 'x': x, 'y': y});
    }
  }

  void sendKeyPress(String key, List<String> mods) {
    if (isConnected.value && _socket != null) {
      _socket!.emit('kp', {'key': key, 'mods': mods});
    }
  }

  void sendHotkey(List<String> keys) {
    if (isConnected.value && _socket != null) {
      _socket!.emit('hk', {'keys': keys});
    }
  }

  void sendHandModeToggle(bool active) {
    if (isConnected.value && _socket != null) {
      _socket!.emit('toggle_hand_mode', {'active': active});
    }
  }
}
