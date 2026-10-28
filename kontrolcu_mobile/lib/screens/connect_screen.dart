import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../services/socket_service.dart';
import 'home_screen.dart';
import 'qr_scanner_screen.dart';

class ConnectScreen extends StatefulWidget {
  const ConnectScreen({Key? key}) : super(key: key);

  @override
  State<ConnectScreen> createState() => _ConnectScreenState();
}

class _ConnectScreenState extends State<ConnectScreen> with SingleTickerProviderStateMixin {
  final TextEditingController _ipController = TextEditingController();
  TabController? _tabController;
  
  bool _isLoading = false;
  String? _errorMessage;
  
  // Bluetooth Scan simulation states
  bool _isBtScanning = false;
  final List<Map<String, String>> _btDevices = [];

  @override
  void initState() {
    super.initState();
    _loadSavedIp();
    _tabController = TabController(length: 2, vsync: this);
    _tabController!.addListener(() {
      if (_tabController!.index == 1 && _btDevices.isEmpty) {
        _simulateBtScan();
      }
    });
  }

  @override
  void dispose() {
    _tabController?.dispose();
    _ipController.dispose();
    super.dispose();
  }

  Future<void> _loadSavedIp() async {
    final prefs = await SharedPreferences.getInstance();
    final savedIp = prefs.getString('server_ip') ?? '';
    if (savedIp.isNotEmpty) {
      _ipController.text = savedIp;
    } else {
      _ipController.text = '192.168.1.103:5556';
    }
  }

  Future<void> _saveIp(String ip) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('server_ip', ip);
  }

  void _handleConnect({String? customUrl}) {
    final ipInput = customUrl ?? _ipController.text.trim();
    if (ipInput.isEmpty) {
      setState(() {
        _errorMessage = 'Lütfen geçerli bir IP adresi girin.';
      });
      return;
    }

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    String url = ipInput;
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      url = 'http://$url';
    }

    SocketService.instance.connect(
      url,
      onSuccess: () {
        _saveIp(ipInput);
        if (mounted) {
          setState(() {
            _isLoading = false;
          });
          Navigator.pushReplacement(
            context,
            MaterialPageRoute(builder: (context) => const HomeScreen()),
          );
        }
      },
      onError: (err) {
        if (mounted) {
          setState(() {
            _isLoading = false;
            _errorMessage = 'Bağlantı başarısız. Aynı WiFi ağında olduğunuzdan emin olun.';
          });
        }
      },
    );
  }

  // Simulate Bluetooth scanning process
  void _simulateBtScan() {
    setState(() {
      _isBtScanning = true;
      _btDevices.clear();
    });

    Future.delayed(const Duration(seconds: 2), () {
      if (mounted) {
        setState(() {
          _isBtScanning = false;
          _btDevices.addAll([
            {'name': '⬡ IRLE-PC-BT (Hazır)', 'address': '00:1A:7D:DA:71:11', 'type': 'irle'},
            {'name': 'Xbox Wireless Controller', 'address': '34:C9:F0:4A:22:9E', 'type': 'gamepad'},
            {'name': 'DESKTOP-ATA-PC', 'address': 'A0:B1:C2:D3:E4:F5', 'type': 'pc'},
          ]);
        });
      }
    });
  }

  void _handleBtConnect(Map<String, String> device) {
    if (device['type'] != 'irle') {
      showDialog(
        context: context,
        builder: (context) => AlertDialog(
          backgroundColor: const Color(0xFF161D2E),
          title: const Text('Uyumsuz Cihaz', style: TextStyle(color: Colors.white)),
          content: Text('${device['name']} bir IRLE sunucusu barındırmıyor.', style: const TextStyle(color: Colors.white70)),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Tamam', style: TextStyle(color: Color(0xFFA78BFA))),
            )
          ],
        ),
      );
      return;
    }

    setState(() {
      _isLoading = true;
    });

    // Simulated BT over Socket connection:
    // In local testing context, we fall back to local IP or show standard instructions
    Future.delayed(const Duration(seconds: 1), () {
      setState(() {
        _isLoading = false;
      });
      showDialog(
        context: context,
        builder: (context) => AlertDialog(
          backgroundColor: const Color(0xFF161D2E),
          title: const Text('Bluetooth Bağlantısı', style: TextStyle(color: Colors.white)),
          content: const Text(
            'Bluetooth eşleşmesi başlatılıyor. PC tarafında Bluetooth Serial sunucusu '
            'aktif edilmediyse, lütfen WiFi (IP) sekmesini kullanarak bağlanın.',
            style: TextStyle(color: Colors.white70),
          ),
          actions: [
            TextButton(
              onPressed: () {
                Navigator.pop(context);
                // Auto switch back to IP for stability
                _tabController?.animateTo(0);
              },
              child: const Text('WiFi ile Bağlan (Önerilen)', style: TextStyle(color: Color(0xFFA78BFA))),
            ),
          ],
        ),
      );
    });
  }

  Future<void> _startQrScan() async {
    final scannedCode = await Navigator.push<String>(
      context,
      MaterialPageRoute(builder: (context) => const QrScannerScreen()),
    );

    if (scannedCode != null && scannedCode.isNotEmpty) {
      String ip = scannedCode;
      // Strip protocol prefix if present
      if (ip.startsWith('http://')) ip = ip.replaceFirst('http://', '');
      if (ip.startsWith('https://')) ip = ip.replaceFirst('https://', '');
      
      setState(() {
        _ipController.text = ip;
      });
      _handleConnect(customUrl: ip);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0F1117),
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 28.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // Logo/Brand Icon
              Center(
                child: Container(
                  width: 72,
                  height: 72,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: const Color(0xFF161D2E),
                    border: Border.all(color: const Color(0xFF6366F1), width: 2),
                    boxShadow: [
                      BoxShadow(
                        color: const Color(0xFF6366F1).withOpacity(0.2),
                        blurRadius: 16,
                        spreadRadius: 4,
                      )
                    ],
                  ),
                  child: const Center(
                    child: Icon(
                      Icons.gamepad,
                      size: 36,
                      color: Color(0xFF6366F1),
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 18),
              const Center(
                child: Text(
                  '⬡ IRLE KONTROLCÜ',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 20,
                    fontWeight: FontWeight.w900,
                    letterSpacing: 1.5,
                  ),
                ),
              ),
              const SizedBox(height: 20),
              
              // Custom Sliding Tabs
              Container(
                height: 44,
                decoration: BoxDecoration(
                  color: const Color(0xFF161D2E),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: const Color(0xFF253350)),
                ),
                child: TabBar(
                  controller: _tabController,
                  indicator: BoxDecoration(
                    borderRadius: BorderRadius.circular(8),
                    color: const Color(0xFF6366F1),
                  ),
                  labelColor: Colors.white,
                  unselectedLabelColor: const Color(0xFF4B5A72),
                  labelStyle: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12),
                  tabs: const [
                    Tab(text: '🌐 WiFi (IP)'),
                    Tab(text: '📡 Bluetooth'),
                  ],
                ),
              ),
              const SizedBox(height: 24),

              // Tab Views Container
              SizedBox(
                height: 220,
                child: TabBarView(
                  controller: _tabController,
                  physics: const NeverScrollableScrollPhysics(), // Handle manually
                  children: [
                    // --- TAB 1: WiFi (IP + QR Scanner) ---
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const Text(
                          'Bilgisayar IP Adresini girin veya QR kodu taratın:',
                          style: TextStyle(color: Color(0xFF4B5A72), fontSize: 12, fontWeight: FontWeight.w600),
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 16),
                        Container(
                          decoration: BoxDecoration(
                            color: const Color(0xFF161D2E),
                            borderRadius: BorderRadius.circular(12),
                            border: Border.all(color: const Color(0xFF253350)),
                          ),
                          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                          child: Row(
                            children: [
                              const Icon(Icons.computer, color: Color(0xFF6366F1), size: 20),
                              const SizedBox(width: 10),
                              Expanded(
                                child: TextField(
                                  controller: _ipController,
                                  style: const TextStyle(color: Colors.white, fontSize: 14, fontFamily: 'monospace'),
                                  keyboardType: TextInputType.url,
                                  decoration: const InputDecoration(
                                    border: InputBorder.none,
                                    hintText: '192.168.1.103:5556',
                                    hintStyle: TextStyle(color: Color(0xFF4B5A72)),
                                  ),
                                ),
                              ),
                              // QR Code scanner button!
                              IconButton(
                                icon: const Icon(Icons.qr_code_scanner, color: Color(0xFFA78BFA)),
                                onPressed: _startQrScan,
                              ),
                            ],
                          ),
                        ),
                        if (_errorMessage != null) ...[
                          const SizedBox(height: 12),
                          Text(
                            _errorMessage!,
                            style: const TextStyle(color: Color(0xFFF87171), fontSize: 11, fontWeight: FontWeight.w600),
                            textAlign: TextAlign.center,
                          ),
                        ],
                        const Spacer(),
                        _isLoading
                            ? const Center(
                                child: CircularProgressIndicator(
                                  valueColor: AlwaysStoppedAnimation<Color>(Color(0xFF6366F1)),
                                ),
                              )
                            : ElevatedButton(
                                onPressed: () => _handleConnect(),
                                style: ElevatedButton.styleFrom(
                                  backgroundColor: const Color(0xFF6366F1),
                                  foregroundColor: Colors.white,
                                  padding: const EdgeInsets.symmetric(vertical: 14),
                                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                                  elevation: 4,
                                ),
                                child: const Text('BAĞLAN', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w800)),
                              ),
                      ],
                    ),

                    // --- TAB 2: Bluetooth Devices List ---
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            const Text(
                              'Yakındaki Bluetooth Cihazları:',
                              style: TextStyle(color: Color(0xFF4B5A72), fontSize: 12, fontWeight: FontWeight.w600),
                            ),
                            if (_isBtScanning)
                              const SizedBox(
                                width: 12,
                                height: 12,
                                child: CircularProgressIndicator(strokeWidth: 1.5, valueColor: AlwaysStoppedAnimation<Color>(Color(0xFFA78BFA))),
                              )
                            else
                              IconButton(
                                constraints: const BoxConstraints(),
                                padding: EdgeInsets.zero,
                                icon: const Icon(Icons.refresh, size: 18, color: Color(0xFFA78BFA)),
                                onPressed: _simulateBtScan,
                              ),
                          ],
                        ),
                        const SizedBox(height: 8),
                        Expanded(
                          child: _isBtScanning
                              ? const Center(
                                  child: Text('Cihazlar aranıyor...', style: TextStyle(color: Color(0xFF4B5A72), fontSize: 12)),
                                )
                              : _btDevices.isEmpty
                                  ? const Center(
                                      child: Text('Cihaz bulunamadı.', style: TextStyle(color: Color(0xFF4B5A72), fontSize: 12)),
                                    )
                                  : ListView.builder(
                                      padding: EdgeInsets.zero,
                                      itemCount: _btDevices.length,
                                      itemBuilder: (context, index) {
                                        final dev = _btDevices[index];
                                        final isIrle = dev['type'] == 'irle';
                                        return Container(
                                          margin: const EdgeInsets.only(bottom: 6),
                                          decoration: BoxDecoration(
                                            color: const Color(0xFF161D2E),
                                            borderRadius: BorderRadius.circular(8),
                                            border: Border.all(color: isIrle ? const Color(0xFF6366F1) : const Color(0xFF253350)),
                                          ),
                                          child: ListTile(
                                            dense: true,
                                            contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 0),
                                            title: Text(dev['name']!, style: TextStyle(color: Colors.white, fontWeight: isIrle ? FontWeight.bold : FontWeight.normal)),
                                            subtitle: Text(dev['address']!, style: const TextStyle(color: Color(0xFF4B5A72), fontSize: 10)),
                                            trailing: Icon(
                                              isIrle ? Icons.bluetooth_connected : Icons.bluetooth,
                                              color: isIrle ? const Color(0xFFA78BFA) : const Color(0xFF253350),
                                              size: 16,
                                            ),
                                            onTap: () => _handleBtConnect(dev),
                                          ),
                                        );
                                      },
                                    ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
