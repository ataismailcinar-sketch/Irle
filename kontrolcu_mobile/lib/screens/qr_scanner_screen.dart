import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

class QrScannerScreen extends StatefulWidget {
  const QrScannerScreen({Key? key}) : super(key: key);

  @override
  State<QrScannerScreen> createState() => _QrScannerScreenState();
}

class _QrScannerScreenState extends State<QrScannerScreen> {
  bool _hasScanned = false;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0F1117),
      appBar: AppBar(
        title: const Text('QR Kod Tara'),
        backgroundColor: const Color(0xFF161D2E),
        elevation: 0,
      ),
      body: Stack(
        children: [
          MobileScanner(
            onDetect: (capture) {
              if (_hasScanned) return;
              final List<Barcode> barcodes = capture.barcodes;
              if (barcodes.isNotEmpty && barcodes.first.rawValue != null) {
                _hasScanned = true;
                final String code = barcodes.first.rawValue!;
                Navigator.pop(context, code);
              }
            },
          ),
          // Scanner Overlay Guide Frame
          Center(
            child: Container(
              width: 250,
              height: 250,
              decoration: BoxDecoration(
                border: Border.all(color: const Color(0xFF6366F1), width: 3),
                borderRadius: BorderRadius.circular(16),
                color: Colors.transparent,
              ),
            ),
          ),
          const Positioned(
            bottom: 40,
            left: 20,
            right: 20,
            child: Text(
              'Bilgisayardaki QR kodu cercevenin icine getirin.',
              style: TextStyle(
                color: Colors.white70,
                fontSize: 13,
                fontWeight: FontWeight.bold,
              ),
              textAlign: TextAlign.center,
            ),
          ),
        ],
      ),
    );
  }
}
