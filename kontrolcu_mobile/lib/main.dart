import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'screens/connect_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  
  // Set preferred orientation (portrait only for standard remote layout)
  SystemChrome.setPreferredOrientations([
    DeviceOrientation.portraitUp,
    DeviceOrientation.portraitDown,
  ]);
  
  // Custom styled system navigation bar
  SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(
    statusBarColor: Colors.transparent,
    statusBarIconBrightness: Brightness.light,
    systemNavigationBarColor: Color(0xFF161D2E),
    systemNavigationBarIconBrightness: Brightness.light,
  ));

  runApp(const IrleControllerApp());
}

class IrleControllerApp extends StatelessWidget {
  const IrleControllerApp({Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'IRLE Controller',
      debugShowCheckedModeBanner: false,
      theme: ThemeData.dark().copyWith(
        scaffoldBackgroundColor: const Color(0xFF0F1117),
        primaryColor: const Color(0xFF6366F1),
        colorScheme: const ColorScheme.dark(
          primary: Color(0xFF6366F1),
          secondary: Color(0xFFA78BFA),
          surface: Color(0xFF161D2E),
          background: const Color(0xFF0F1117),
        ),
        // Slider Custom Theme
        sliderTheme: SliderTheme.of(context).copyWith(
          activeTrackColor: const Color(0xFF6366F1),
          inactiveTrackColor: const Color(0xFF253350),
          trackHeight: 4.0,
          thumbColor: const Color(0xFFA78BFA),
          thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 10.0),
          overlayColor: const Color(0xFF6366F1).withAlpha(32),
          overlayShape: const RoundSliderOverlayShape(overlayRadius: 20.0),
        ),
      ),
      home: const ConnectScreen(),
    );
  }
}
