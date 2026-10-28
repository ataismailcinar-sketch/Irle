# -*- coding: utf-8 -*-
"""
=============================================================================
ADAPTERS / INTENT / RULE ENGINE — Türkçe Regex Tabanlı Komut Ayrıştırıcı
=============================================================================
Bu modülün TEK sorumluluğu:
    Türkçe metni alıp typed Command veya Query nesnesi döndürmek.

OS işlemleri YOK. Event bus bağımlılığı YOK. Saf fonksiyon mantığı.

Eski `modules/llm_modulu.py` içindeki `RuleEngine` sınıfından farkı:
  - Handler'lar `subprocess`, `ctypes`, `sbc`, `pyautogui` vb. ÇAĞIRMAZ.
  - Sadece doğru typed Command/Query nesnesi oluşturur.
  - OS komutlarını çalıştırmak `AksiyonModulu`'nun (Milestone 2) işidir.

Döndürülen tipler:
  - `Command`  → yan etki yaratacak bir işlem talebi
  - `Query`    → bilgi sorgulama talebi
  - `None`     → hiçbir kural eşleşmedi

Kullanım:
    from src.irle.adapters.intent.rule_engine import RuleEngine
    engine = RuleEngine()
    result = engine.parse("bilgisayarı kapat")
    # → ShutdownComputer(delay_seconds=60)
=============================================================================
"""

from __future__ import annotations

import logging
import re
from typing import Union

from irle.domain.commands import (
    CancelAllTimers,
    CancelShutdown,
    ClearClipboard,
    CloseApplication,
    CreateFolder,
    CreateNote,
    DeleteNote,
    KillProcess,
    LockComputer,
    MediaControl,
    MouseClick,
    MuteVolume,
    OpenApplication,
    ReadClipboard,
    RestartComputer,
    ScheduleCommand,
    SearchFile,
    SearchWeb,
    SetBrightness,
    SetVolume,
    ShutdownComputer,
    Speak,
    TakeScreenshot,
    WindowControl,
)
from irle.domain.queries import (
    GetBatteryStatus,
    GetCurrentTime,
    GetNetworkStatus,
    GetSystemInfo,
    ListNotes,
)

logger = logging.getLogger("irle.adapters.intent.rule_engine")

# Döndürülebilecek tip birliği
ParseResult = Union[
    # Commands
    CancelAllTimers, CancelShutdown, ClearClipboard, CloseApplication,
    CreateFolder, CreateNote, DeleteNote, KillProcess, LockComputer,
    MediaControl, MouseClick, MuteVolume, OpenApplication, ReadClipboard,
    RestartComputer, ScheduleCommand, SearchFile, SearchWeb, SetBrightness,
    SetVolume, ShutdownComputer, Speak, TakeScreenshot, WindowControl,
    # Queries
    GetBatteryStatus, GetCurrentTime, GetNetworkStatus, GetSystemInfo, ListNotes,
    None,
]

# ---------------------------------------------------------------------------
# Sabitler: Sık kullanılan regex parçaları
# ---------------------------------------------------------------------------
_NUMBER = r"(\d+)"
_VOLUME_KEYWORD = r"(ses|volume|ses\s+seviyesi)"
_BRIGHTNESS_KEYWORD = r"(parlaklık|ışık|ekran\s+parlaklığı)"
_MEDIA_KEYWORD = r"(müzik|video|medya|şarkı)"
_PC_KEYWORD = r"(pc|bilgisayar|sistem|makine)"


class RuleEngine:
    """
    Türkçe sesli komut metnini typed Command/Query'ye dönüştürür.

    Thread-safe. Durum tutmaz — her `parse()` çağrısı bağımsızdır.
    """

    def __init__(self) -> None:
        # (derlenmiş_regex, handler_callable) çiftleri — öncelik sırasına göre
        self._rules: list[tuple[re.Pattern[str], object]] = self._build_rules()

    # ------------------------------------------------------------------
    # Ana giriş noktası
    # ------------------------------------------------------------------

    def parse(self, text: str) -> ParseResult:
        """Metni ayrıştır ve typed sonuç döndür.

        Args:
            text: Kullanıcının söylediği metin (büyük/küçük harf farketmez).

        Returns:
            Eşleşen Command/Query nesnesi, eşleşme yoksa None.
        """
        normalized = text.lower().strip()
        for pattern, handler in self._rules:
            match = pattern.search(normalized)
            if match:
                try:
                    result = handler(match)  # type: ignore[operator]
                    if result is not None:
                        logger.debug(
                            "Kural eşleşti: '%s' → %s",
                            pattern.pattern[:60],
                            type(result).__name__,
                        )
                    return result
                except Exception as exc:
                    logger.error(
                        "Kural handler hatası (pattern=%r): %s",
                        pattern.pattern[:60],
                        exc,
                    )
                    return None
        logger.debug("Hiçbir kural eşleşmedi: '%s'", normalized[:80])
        return None

    # ------------------------------------------------------------------
    # Kural inşası
    # ------------------------------------------------------------------

    def _build_rules(self) -> list[tuple[re.Pattern[str], object]]:
        """Tüm kural listesini derle. Sıralama önemlidir — ilk eşleşen kazanır."""

        def r(pattern: str) -> re.Pattern[str]:
            return re.compile(pattern, re.IGNORECASE | re.UNICODE)

        rules: list[tuple[re.Pattern[str], object]] = [

            # ----------------------------------------------------------------
            # SİSTEM GÜCÜ (en yüksek öncelik — kritik komutlar)
            # ----------------------------------------------------------------
            (
                r(rf"{_PC_KEYWORD}.*(kapat|sustur|power\s+off|shut\s*down)"),
                lambda m: ShutdownComputer(delay_seconds=60),
            ),
            (
                r(rf"{_PC_KEYWORD}.*(yeniden\s+başlat|restart|reboot)"),
                lambda m: RestartComputer(delay_seconds=60),
            ),
            (
                r(rf"(bilgisayar|ekran).*(kilitle|lock)"),
                lambda m: LockComputer(),
            ),
            (
                r(r"(kapatmayı\s+iptal|shutdown\s+iptal|kapanmayı\s+durdur)"),
                lambda m: CancelShutdown(),
            ),

            # ----------------------------------------------------------------
            # DONANIM / DURUM SORGULARI
            # ----------------------------------------------------------------
            (
                r(r"(pil|batarya).*(durum|yüzde|ne\s+kadar|oran)"),
                lambda m: GetBatteryStatus(),
            ),
            (
                r(r"(ekran\s+kartı|gpu).*(nedir|durum|bilgi|model)"),
                lambda m: GetSystemInfo(topics=("gpu",)),
            ),
            (
                r(r"(disk|depolama|sürücü).*(durum|boş|dolu|kaç)"),
                lambda m: GetSystemInfo(topics=("disk",)),
            ),
            (
                r(r"(işlemci|cpu|ram|bellek|performans).*(durum|yüzde|ne\s+kadar|kaç)"),
                lambda m: GetSystemInfo(topics=("cpu", "ram")),
            ),
            (
                r(r"(donanım|sistem).*(bilgi|durum|nedir|ne)"),
                lambda m: GetSystemInfo(),
            ),

            # ----------------------------------------------------------------
            # ZAMANLAYICI — Medya/Ses/Parlaklık kurallarından ÖNCE gelmeli
            # Aksi halde "3 dakika sonra müziği duraklat" medya kuralı yakalar.
            # ----------------------------------------------------------------
            (
                r(r"(zamanlayıcıy?\u0131|sayacı|görevi)\s+(iptal|durdur|kapat)"),
                lambda m: CancelAllTimers(),
            ),
            (
                r(r"(\d+)\s+(dakika|saniye)\s+sonra\s+(.+)"),
                lambda m: ScheduleCommand(
                    delay_seconds=int(m.group(1)) * (60 if "dakika" in m.group(2) else 1),
                    inner_command_text=m.group(3).strip(),
                ),
            ),

            # ----------------------------------------------------------------
            # SES KONTROLİ
            # ----------------------------------------------------------------
            (
                r(rf"{_VOLUME_KEYWORD}.*(yüzde|%)\s*{_NUMBER}"),
                lambda m: SetVolume(level=int(m.group(3))),
            ),
            (
                r(rf"{_NUMBER}\s*(yüzde|%)\s*ses"),
                lambda m: SetVolume(level=int(m.group(1))),
            ),
            (
                r(rf"{_VOLUME_KEYWORD}.*(arttır|yükselt|aç|büyüt)"),
                lambda m: SetVolume(delta=+10),
            ),
            (
                r(rf"{_VOLUME_KEYWORD}.*(azalt|kıs|düşür|küçült)"),
                lambda m: SetVolume(delta=-10),
            ),
            (
                r(rf"{_VOLUME_KEYWORD}.*(sustur|kapat|mute|kapat)"),
                lambda m: MuteVolume(),
            ),

            # ----------------------------------------------------------------
            # PARLAKLIK KONTROLİ
            # ----------------------------------------------------------------
            (
                r(rf"{_BRIGHTNESS_KEYWORD}.*(yüzde|%)\s*{_NUMBER}"),
                lambda m: SetBrightness(level=int(m.group(3))),
            ),
            (
                r(rf"{_NUMBER}\s*(yüzde|%)\s*(parlaklık|ışık)"),
                lambda m: SetBrightness(level=int(m.group(1))),
            ),
            (
                # arttır, artır, yükselt, aç — isim çekimi ekleri tolere edilir
                r(r"(parlaklı[kğı]+|ışı[kğı]+|ekran\s+parlaklı[kğı]+).*(arttır|artır|yükselt|aç)"),
                lambda m: SetBrightness(delta=+10),
            ),
            (
                r(r"(parlaklı[kğı]+|ışı[kğı]+|ekran\s+parlaklı[kğı]+).*(azalt|kıs|düşür)"),
                lambda m: SetBrightness(delta=-10),
            ),

            # ----------------------------------------------------------------
            # MEDYA KONTROLİ
            # ----------------------------------------------------------------
            (
                # müzik/müziği/video/medya + duraklat/durdur/pause
                r(r"(müzi[kği]+|video\w*|medya\w*|şarkı\w*).*(durdur|duraklat|pause)"),
                lambda m: MediaControl(action="play_pause"),
            ),
            (
                r(r"(müzi[kği]+|video\w*|medya\w*|şarkı\w*).*(oynat|başlat|play|devam)"),
                lambda m: MediaControl(action="play_pause"),
            ),
            (
                r(r"(müzi[kği]+|video\w*|medya\w*|şarkı\w*).*(sonraki|next|ileri)"),
                lambda m: MediaControl(action="next"),
            ),
            (
                r(r"(müzi[kği]+|video\w*|medya\w*|şarkı\w*).*(önceki|prev|geri|önce)"),
                lambda m: MediaControl(action="previous"),
            ),

            # ----------------------------------------------------------------
            # SAAT — genel uygulama açma kuralından ÖNCE gelmeli
            # ----------------------------------------------------------------
            (
                r(r"(saat|zaman)\s*(kaç|nedir|ne|söyle)"),
                lambda m: GetCurrentTime(),
            ),
            (
                r(r"(bugün\s+)?tarih\s*(nedir|kaç|ne|söyle)?"),
                lambda m: GetCurrentTime(),
            ),

            # ----------------------------------------------------------------
            # EKRAN GÖRÜNTÜSÜ
            # ----------------------------------------------------------------
            (
                r(r"(ekran\s+görüntüsü|screenshot|ekran\s+ss|ss\s+al)"),
                lambda m: TakeScreenshot(),
            ),

            # ----------------------------------------------------------------
            # PENCERE / SÜREÇ YÖNETİMİ
            # ----------------------------------------------------------------
            (
                r(r"(pencere|uygulama)\s+(öne\s+getir|odaklan)\s+(.+)"),
                lambda m: WindowControl(app_name=m.group(3).strip(), action="focus"),
            ),
            (
                r(r"(pencere|uygulama)\s+(tam\s+ekran|maximize)\s+(.+)"),
                lambda m: WindowControl(app_name=m.group(3).strip(), action="maximize"),
            ),
            (
                r(r"(pencere|uygulama)\s+(küçült|minimize)\s+(.+)"),
                lambda m: WindowControl(app_name=m.group(3).strip(), action="minimize"),
            ),
            (
                r(r"(pencere|uygulama)\s+kapat\s+(.+)"),
                lambda m: WindowControl(app_name=m.group(2).strip(), action="close"),
            ),
            (
                r(r"(.+)\s+(zorla\s+kapat|sonlandır|kill|öldür)"),
                lambda m: KillProcess(process_name=m.group(1).strip()),
            ),

            # ----------------------------------------------------------------
            # AĞ
            # ----------------------------------------------------------------
            (
                r(r"ip\s+(adresim|adresini|nedir)"),
                lambda m: GetNetworkStatus(),
            ),
            (
                r(r"(internet|bağlantı|network).*(durum|hız|gecikme|ping|test)"),
                lambda m: GetNetworkStatus(include_ping="ping" in m.group(0) or "gecikme" in m.group(0)),
            ),

            # ----------------------------------------------------------------
            # PANO
            # ----------------------------------------------------------------
            (
                r(r"panoda\s+ne\s+(var|yazıyor|yazılı)"),
                lambda m: ReadClipboard(),
            ),
            (
                r(r"panoyu\s+(temizle|boşalt|sil)"),
                lambda m: ClearClipboard(),
            ),

            # ----------------------------------------------------------------
            # NOTLAR
            # ----------------------------------------------------------------
            (
                r(r"not\s+al[:\s]+(.+)"),
                lambda m: CreateNote(text=m.group(1).strip()),
            ),
            (
                r(r"notlarımı\s+(oku|listele|göster|getir)"),
                lambda m: ListNotes(limit=3),
            ),
            (
                r(r"son\s+notu?\s+sil"),
                lambda m: DeleteNote(mode="last"),
            ),
            (
                r(r"(tüm|bütün)\s+notları?\s+sil"),
                lambda m: DeleteNote(mode="all"),
            ),

            # ----------------------------------------------------------------
            # DOSYA İŞLEMLERİ
            # ----------------------------------------------------------------
            (
                r(r"masaüstünde\s+(.+)\s+(ara|bul|bul\s+bana)"),
                lambda m: SearchFile(term=m.group(1).strip()),
            ),
            (
                r(r"(klasör|dizin|folder)\s+(oluştur|yarat|aç|yap)\s+(.+)"),
                lambda m: CreateFolder(name=m.group(3).strip()),
            ),

            # ----------------------------------------------------------------
            # WEB ARAMA
            # ----------------------------------------------------------------
            (
                r(r"(.+)\s+(internette|google'da|google\s+da|web'de)\s*(ara|bul|araştır)"),
                lambda m: SearchWeb(query=m.group(1).strip()),
            ),
            (
                r(r"(google|web|internet)\s*'?\s*da\s+(.+)\s+ara"),
                lambda m: SearchWeb(query=m.group(2).strip()),
            ),

            # ----------------------------------------------------------------
            # UYGULAMA AÇ (geniş kapsamlı — diğer kurallardan sonra)
            # ----------------------------------------------------------------
            (
                r(r"(notepad|not\s+defteri)\s*(aç|başlat|çalıştır)?"),
                lambda m: OpenApplication(name="notepad"),
            ),
            (
                r(r"(hesap\s+makinesi|calculator|calc)\s*(aç|başlat)?"),
                lambda m: OpenApplication(name="hesap"),
            ),
            (
                r(r"(dosya\s+gezgini|explorer|klasörü?\s+aç)\s*(aç|başlat)?"),
                lambda m: OpenApplication(name="explorer"),
            ),
            (
                r(r"(chrome|firefox|tarayıcı|browser)\s*(aç|başlat)?"),
                lambda m: OpenApplication(name="chrome"),
            ),
            (
                r(r"(terminal|komut\s+istemi|cmd|powershell)\s*(aç|başlat)?"),
                lambda m: OpenApplication(name="terminal"),
            ),
            (
                r(r"(spotify|müzik\s+uygulaması)\s*(aç|başlat)?"),
                lambda m: OpenApplication(name="spotify"),
            ),
            (
                r(r"(discord)\s*(aç|başlat)?"),
                lambda m: OpenApplication(name="discord"),
            ),
            (
                r(r"(steam)\s*(aç|başlat)?"),
                lambda m: OpenApplication(name="steam"),
            ),
            (
                r(r"(vs\s*code|visual\s+studio\s+code|vscode)\s*(aç|başlat)?"),
                lambda m: OpenApplication(name="code"),
            ),
            # Genel uygulama açma — "X aç / X'i aç / X'ı aç"
            (
                r(r"(.+?)\s*'?[iıuü]?\s*(aç|başlat|çalıştır|başlat)"),
                self._parse_generic_open,
            ),

            # ----------------------------------------------------------------
            # SELAMLAMA / KİŞİLİK
            # ----------------------------------------------------------------
            (
                r(r"(merhaba|selam|hey|nasılsın|naber|günaydın|iyi\s+günler)"),
                lambda m: Speak(
                    text="Merhaba! Ben Irle, tamamen çevrimdışı modda bile emirlerini yerine getirmeye hazırım."
                ),
            ),
        ]

        return rules

    # ------------------------------------------------------------------
    # Yardımcı handler'lar
    # ------------------------------------------------------------------

    def _parse_generic_open(self, match: re.Match) -> ParseResult:
        """Genel 'X aç' kalıbından uygulama adını çıkar."""
        candidate = match.group(1).strip()
        # Çok kısa veya sadece dolgu kelimeler ise geç
        stop_words = {
            "bir", "bu", "şu", "o", "lütfen", "acaba",
            "tamam", "şimdi", "ne", "nasıl",
        }
        if len(candidate) < 2 or candidate in stop_words:
            return None
        return OpenApplication(name=candidate)
