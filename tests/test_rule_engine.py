# -*- coding: utf-8 -*-
"""
=============================================================================
TEST — Türkçe Kural Motoru (src/irle/adapters/intent/rule_engine.py)
=============================================================================
Her test bir Türkçe sesli komut metnini parse eder ve beklenen typed
Command/Query nesnesini döndürdüğünü doğrular.
"""

import pytest

from irle.adapters.intent.rule_engine import RuleEngine
from irle.domain.commands import (
    CancelAllTimers,
    ClearClipboard,
    CreateNote,
    DeleteNote,
    LockComputer,
    MediaControl,
    MuteVolume,
    OpenApplication,
    ReadClipboard,
    RestartComputer,
    ScheduleCommand,
    SearchWeb,
    SetBrightness,
    SetVolume,
    ShutdownComputer,
    Speak,
    TakeScreenshot,
)
from irle.domain.queries import (
    GetBatteryStatus,
    GetCurrentTime,
    GetNetworkStatus,
    GetSystemInfo,
    ListNotes,
)


@pytest.fixture
def engine() -> RuleEngine:
    """Test başına yeni bir RuleEngine örneği."""
    return RuleEngine()


# ---------------------------------------------------------------------------
# Sistem Gücü
# ---------------------------------------------------------------------------

class TestSistemGucu:
    def test_bilgisayari_kapat(self, engine):
        result = engine.parse("bilgisayarı kapat")
        assert isinstance(result, ShutdownComputer)
        assert result.delay_seconds == 60

    def test_pc_kapat(self, engine):
        result = engine.parse("pc'yi kapat")
        assert isinstance(result, ShutdownComputer)

    def test_bilgisayar_yeniden_baslat(self, engine):
        result = engine.parse("bilgisayarı yeniden başlat")
        assert isinstance(result, RestartComputer)

    def test_sistemi_restart_et(self, engine):
        result = engine.parse("sistemi restart et")
        assert isinstance(result, RestartComputer)

    def test_ekrani_kilitle(self, engine):
        result = engine.parse("ekranı kilitle")
        assert isinstance(result, LockComputer)

    def test_bilgisayar_kilitle(self, engine):
        result = engine.parse("bilgisayarı kilitle")
        assert isinstance(result, LockComputer)


# ---------------------------------------------------------------------------
# Ses Kontrolü
# ---------------------------------------------------------------------------

class TestSesKontrolu:
    def test_ses_artir(self, engine):
        result = engine.parse("sesi arttır")
        assert isinstance(result, SetVolume)
        assert result.delta is not None and result.delta > 0
        assert result.level is None

    def test_ses_azalt(self, engine):
        result = engine.parse("sesi azalt")
        assert isinstance(result, SetVolume)
        assert result.delta is not None and result.delta < 0

    def test_ses_yuzde_50(self, engine):
        result = engine.parse("ses yüzde 50")
        assert isinstance(result, SetVolume)
        assert result.level == 50
        assert result.delta is None

    def test_volume_yuzde_80(self, engine):
        result = engine.parse("volume yüzde 80 ayarla")
        assert isinstance(result, SetVolume)
        assert result.level == 80

    def test_ses_sustur(self, engine):
        result = engine.parse("sesi sustur")
        assert isinstance(result, MuteVolume)

    def test_ses_mute(self, engine):
        result = engine.parse("volume mute")
        assert isinstance(result, MuteVolume)


# ---------------------------------------------------------------------------
# Parlaklık Kontrolü
# ---------------------------------------------------------------------------

class TestParlaklikKontrolu:
    def test_parlaklik_artir(self, engine):
        result = engine.parse("parlaklığı arttır")
        assert isinstance(result, SetBrightness)
        assert result.delta is not None and result.delta > 0

    def test_parlaklik_azalt(self, engine):
        result = engine.parse("parlaklığı azalt")
        assert isinstance(result, SetBrightness)
        assert result.delta is not None and result.delta < 0

    def test_parlaklik_yuzde_70(self, engine):
        result = engine.parse("parlaklık yüzde 70")
        assert isinstance(result, SetBrightness)
        assert result.level == 70

    def test_isik_yuzde_30(self, engine):
        result = engine.parse("ışık yüzde 30 yap")
        assert isinstance(result, SetBrightness)
        assert result.level == 30


# ---------------------------------------------------------------------------
# Medya Kontrolü
# ---------------------------------------------------------------------------

class TestMedyaKontrolu:
    def test_muzik_duraklat(self, engine):
        result = engine.parse("müziği duraklat")
        assert isinstance(result, MediaControl)
        assert result.action == "play_pause"

    def test_muzik_oynat(self, engine):
        result = engine.parse("müziği oynat")
        assert isinstance(result, MediaControl)
        assert result.action == "play_pause"

    def test_sonraki_sarki(self, engine):
        result = engine.parse("müziği sonrakine geçir")
        assert isinstance(result, MediaControl)
        assert result.action == "next"

    def test_onceki_sarki(self, engine):
        result = engine.parse("müziği öncekine geçir")
        assert isinstance(result, MediaControl)
        assert result.action == "previous"


# ---------------------------------------------------------------------------
# Pil
# ---------------------------------------------------------------------------

class TestPil:
    def test_pil_durumu(self, engine):
        result = engine.parse("pil durumu nedir")
        assert isinstance(result, GetBatteryStatus)

    def test_batarya_yuzdesi(self, engine):
        result = engine.parse("batarya yüzdesi ne kadar")
        assert isinstance(result, GetBatteryStatus)


# ---------------------------------------------------------------------------
# Notlar
# ---------------------------------------------------------------------------

class TestNotlar:
    def test_not_al(self, engine):
        result = engine.parse("not al: yarın toplantı var")
        assert isinstance(result, CreateNote)
        assert "yarın toplantı var" in result.text

    def test_not_al_iki_nokta_bosluk(self, engine):
        result = engine.parse("not al: alışveriş listesi")
        assert isinstance(result, CreateNote)
        assert result.text == "alışveriş listesi"

    def test_notlarimi_listele(self, engine):
        result = engine.parse("notlarımı listele")
        assert isinstance(result, ListNotes)

    def test_notlarimi_oku(self, engine):
        result = engine.parse("notlarımı oku")
        assert isinstance(result, ListNotes)

    def test_son_notu_sil(self, engine):
        result = engine.parse("son notu sil")
        assert isinstance(result, DeleteNote)
        assert result.mode == "last"

    def test_tum_notlari_sil(self, engine):
        result = engine.parse("tüm notları sil")
        assert isinstance(result, DeleteNote)
        assert result.mode == "all"


# ---------------------------------------------------------------------------
# Web Arama
# ---------------------------------------------------------------------------

class TestWebArama:
    def test_internette_ara(self, engine):
        result = engine.parse("python öğren internette ara")
        assert isinstance(result, SearchWeb)
        assert "python" in result.query.lower()

    def test_google_da_ara(self, engine):
        result = engine.parse("google'da hava durumu ara")
        assert isinstance(result, SearchWeb)
        assert "hava durumu" in result.query.lower()


# ---------------------------------------------------------------------------
# Uygulama Açma
# ---------------------------------------------------------------------------

class TestUygulamaAc:
    def test_notepad(self, engine):
        result = engine.parse("notepad aç")
        assert isinstance(result, OpenApplication)
        assert result.name == "notepad"

    def test_not_defteri(self, engine):
        result = engine.parse("not defteri aç")
        assert isinstance(result, OpenApplication)
        assert result.name == "notepad"

    def test_hesap_makinesi(self, engine):
        result = engine.parse("hesap makinesi aç")
        assert isinstance(result, OpenApplication)
        assert result.name == "hesap"

    def test_chrome(self, engine):
        result = engine.parse("chrome aç")
        assert isinstance(result, OpenApplication)
        assert result.name == "chrome"

    def test_terminal(self, engine):
        result = engine.parse("terminal aç")
        assert isinstance(result, OpenApplication)
        assert result.name == "terminal"

    def test_spotify(self, engine):
        result = engine.parse("spotify aç")
        assert isinstance(result, OpenApplication)
        assert result.name == "spotify"


# ---------------------------------------------------------------------------
# Saat Sorgusu
# ---------------------------------------------------------------------------

class TestSaat:
    def test_saat_kac(self, engine):
        result = engine.parse("saat kaç")
        assert isinstance(result, GetCurrentTime)

    def test_zaman_nedir(self, engine):
        result = engine.parse("zaman nedir")
        assert isinstance(result, GetCurrentTime)


# ---------------------------------------------------------------------------
# Selamlama
# ---------------------------------------------------------------------------

class TestSelamlama:
    def test_merhaba(self, engine):
        result = engine.parse("merhaba")
        assert isinstance(result, Speak)
        assert len(result.text) > 0

    def test_selam(self, engine):
        result = engine.parse("selam")
        assert isinstance(result, Speak)


# ---------------------------------------------------------------------------
# Ekran Görüntüsü
# ---------------------------------------------------------------------------

class TestEkranGoruntusu:
    def test_screenshot_al(self, engine):
        result = engine.parse("ekran görüntüsü al")
        assert isinstance(result, TakeScreenshot)

    def test_ss_al(self, engine):
        result = engine.parse("ss al")
        assert isinstance(result, TakeScreenshot)


# ---------------------------------------------------------------------------
# Pano
# ---------------------------------------------------------------------------

class TestPano:
    def test_panoda_ne_yazıyor(self, engine):
        result = engine.parse("panoda ne yazıyor")
        assert isinstance(result, ReadClipboard)

    def test_panoyu_temizle(self, engine):
        result = engine.parse("panoyu temizle")
        assert isinstance(result, ClearClipboard)


# ---------------------------------------------------------------------------
# Zamanlayıcı
# ---------------------------------------------------------------------------

class TestZamanLayici:
    def test_3_dakika_sonra(self, engine):
        result = engine.parse("3 dakika sonra müziği duraklat")
        assert isinstance(result, ScheduleCommand)
        assert result.delay_seconds == 180
        assert "müzik" in result.inner_command_text.lower() or "duraklat" in result.inner_command_text.lower()

    def test_30_saniye_sonra(self, engine):
        result = engine.parse("30 saniye sonra ekran görüntüsü al")
        assert isinstance(result, ScheduleCommand)
        assert result.delay_seconds == 30

    def test_zamanlayici_iptal(self, engine):
        result = engine.parse("zamanlayıcıyı iptal et")
        assert isinstance(result, CancelAllTimers)


# ---------------------------------------------------------------------------
# Ağ
# ---------------------------------------------------------------------------

class TestAg:
    def test_internet_durumu(self, engine):
        result = engine.parse("internet durumu nedir")
        assert isinstance(result, GetNetworkStatus)

    def test_ip_adresi(self, engine):
        result = engine.parse("ip adresim nedir")
        assert isinstance(result, GetNetworkStatus)

    def test_ping_testi(self, engine):
        result = engine.parse("bağlantı gecikme ne kadar")
        assert isinstance(result, GetNetworkStatus)
        assert result.include_ping is True


# ---------------------------------------------------------------------------
# Sistem Bilgisi
# ---------------------------------------------------------------------------

class TestSistemBilgisi:
    def test_pil_sorgusu_query(self, engine):
        result = engine.parse("pil yüzdesi ne")
        assert isinstance(result, GetBatteryStatus)

    def test_cpu_durumu(self, engine):
        result = engine.parse("işlemci durumu ne kadar")
        assert isinstance(result, GetSystemInfo)

    def test_disk_durumu(self, engine):
        result = engine.parse("disk durumu ne kadar boş")
        assert isinstance(result, GetSystemInfo)


# ---------------------------------------------------------------------------
# Eşleşme Yok
# ---------------------------------------------------------------------------

class TestEslesmeyok:
    def test_anlamsiz_giris(self, engine):
        result = engine.parse("asdfghjkl qwerty")
        # Hiçbir kural eşleşmemeli — None veya Speak (selamlama değil)
        assert result is None or isinstance(result, (Speak, OpenApplication))

    def test_bos_metin(self, engine):
        result = engine.parse("")
        assert result is None
