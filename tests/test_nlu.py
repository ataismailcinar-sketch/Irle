# -*- coding: utf-8 -*-
"""
=============================================================================
TEST — Dil modelsiz anlama motoru, bağlam, cevap şablonları, uyandırma,
       zamanlayıcı, pencere/süreç, yankı kilidi ve çevrimdışı uçtan uca akış
=============================================================================
"""

from __future__ import annotations

import random
from unittest.mock import MagicMock

import pytest

from irle.adapters.brain.persona import UslupAnalizcisi, UslupProfili
from irle.adapters.intent.nlu import Baglam, TurkceNLU, jetonla, komut_kategorisi
from irle.adapters.intent.uyandirma import UyandirmaFiltresi
from irle.adapters.intent.yanitlar import YanitUretici, agiz_sec
from irle.domain.commands import (
    CancelAllTimers, CloseApplication, CompositeCommand, CreateNote, DeleteNote, KillProcess,
    LockComputer, MediaControl, MuteVolume, OpenApplication, ScheduleCommand, SearchFile,
    SearchWeb, SetBrightness, SetVolume, Speak, TakeScreenshot, WindowControl,
)
from irle.domain.events import SpeechRecognized, TtsRequested
from irle.domain.queries import GetBatteryStatus, GetCurrentTime, GetSystemInfo, ListNotes
from irle.handlers.timer_handler import TimerHandler
from irle.handlers.window_handler import WindowHandler
from irle.infra.command_bus import CommandBus
from irle.infra.echo_guard import EchoGuard
from irle.infra.event_bus import TypedEventBus


NLU = TurkceNLU()


def anla(metin, baglam=None):
    return NLU.anla(metin, baglam)


# ---------------------------------------------------------------------------
# Normalleştirme
# ---------------------------------------------------------------------------

class TestJetonla:

    @pytest.mark.parametrize("metin,beklenen", [
        ("sesi yüzde kırk beş yap", [45]),
        ("sesi 30'a çek", [30]),
        ("on dakika sonra", [10]),
        ("yüzde yüz", [100]),
        ("kırka indir", [40]),
        ("bir şarkı aç", []),           # "bir" burada sayı değil
        ("onu kapat", []),              # "onu" sayı değil
        ("bir dakika sonra", [1]),
    ])
    def test_sayilar(self, metin, beklenen):
        assert [t.sayi for t in jetonla(metin) if t.sayi is not None] == beklenen

    def test_turkce_buyuk_harf_ve_kesme(self):
        kelimeler = [t.metin for t in jetonla("İRLE, Spotify'ı AÇ!")]
        assert kelimeler == ["irle", "spotify", "aç"]

    def test_hedef_eki(self):
        t = [t for t in jetonla("sesi kırka indir") if t.sayi][0]
        assert t.ek == "a"


# ---------------------------------------------------------------------------
# Niyetler
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("metin,komut", [
    # ses
    ("sesi kıs", SetVolume(delta=-15)),
    ("abi şu müziği biraz alçalt da kafam şişti", SetVolume(delta=-10)),
    ("sesi kısar mısınız lütfen", SetVolume(delta=-15)),
    ("sesi çok aç", SetVolume(delta=30)),
    ("sesi 20 artır", SetVolume(delta=20)),
    ("sesi yüzde kırk beş yap", SetVolume(level=45)),
    ("sesi 30'a çek", SetVolume(level=30)),
    ("sesi kapat", MuteVolume()),
    ("sessize al", MuteVolume()),
    # parlaklık
    ("ekranı karart", SetBrightness(delta=-15)),
    ("parlaklığı yüzde elli yap", SetBrightness(level=50)),
    # medya
    ("şarkıyı geç", MediaControl(action="next")),
    ("sonraki şarkı", MediaControl(action="next")),
    ("müziği durdur", MediaControl(action="play_pause")),
    ("müziği aç", MediaControl(action="play_pause")),
    # uygulama
    ("spotify'ı aç", OpenApplication(name="spotify")),
    ("kroma aç", OpenApplication(name="chrome")),                 # STT hatası
    ("not defterini aç", OpenApplication(name="notepad")),
    ("vs code aç", OpenApplication(name="code")),
    ("youtube aç", OpenApplication(name="https://www.youtube.com")),
    ("chrome'u kapat", CloseApplication(name="Chrome")),
    ("discord'u zorla kapat", KillProcess(process_name="discord")),
    ("chrome'u küçült", WindowControl(app_name="Chrome", action="minimize")),
    # bilgi
    ("saat kaç", GetCurrentTime()),
    ("bugün ayın kaçı", GetCurrentTime()),
    ("pil ne durumda", GetBatteryStatus()),
    ("ram ne kadar dolu", GetSystemInfo(topics=("ram",))),
    # not
    ("not al süt almayı unutma", CreateNote(text="süt almayı unutma")),
    ("yarın toplantı var diye not al", CreateNote(text="yarın toplantı var")),
    ("notlarımı oku", ListNotes(limit=3)),
    ("son notu sil", DeleteNote(mode="last")),
    ("tüm notları sil", DeleteNote(mode="all")),
    # ekran / sistem
    ("ekran görüntüsü al", TakeScreenshot()),
    ("ss al", TakeScreenshot()),
    ("bilgisayarı kilitle", LockComputer()),
    # zamanlayıcı
    ("5 dakika sonra çayı hatırlat", ScheduleCommand(delay_seconds=300, inner_command_text="çayı hatırlat")),
    ("on dakika sonra müziği durdur", ScheduleCommand(delay_seconds=600, inner_command_text="müziği durdur")),
    ("yarım saat sonra bana su içmeyi hatırlat",
     ScheduleCommand(delay_seconds=1800, inner_command_text="su içmeyi hatırlat")),
    ("zamanlayıcıyı iptal et", CancelAllTimers()),
    # arama
    ("google'da ankara hava durumu ara", SearchWeb(query="ankara hava durumu")),
    ("masaüstünde rapor dosyasını bul", SearchFile(term="rapor")),
])
def test_niyet(metin, komut):
    r = anla(metin)
    assert r is not None, metin
    assert r.komut == komut
    assert r.guven >= 0.8, (metin, r.guven)


def test_bilesik_komut():
    r = anla("spotify'ı aç ve sesi kıs")
    assert r.komut == CompositeCommand(commands=(OpenApplication(name="spotify"), SetVolume(delta=-15)))


def test_bilesik_parcadan_biri_anlasilmazsa_none():
    assert anla("spotify'ı aç ve bana hayatın anlamını anlat") is None


@pytest.mark.parametrize("metin", [
    "dünyanın en yüksek dağı hangisi",
    "bugün ne yapsam bilemedim",
    "pencereyi açıklar mısın",
])
def test_anlasilmayanlar_beyne_kalir(metin):
    r = anla(metin)
    assert r is None or r.guven < 0.8


def test_bilinmeyen_uygulama_dusuk_guven():
    r = anla("photoshop aç")
    assert r.komut == OpenApplication(name="photoshop")
    assert 0.5 <= r.guven < 0.8


@pytest.mark.parametrize("metin", ["sesi kısma", "müziği durdurma", "chrome'u açma"])
def test_olumsuz(metin):
    r = anla(metin)
    assert r.tur == "olumsuz" and r.komut is None


@pytest.mark.parametrize("metin,niyet", [
    ("selam", "selam"), ("naber kanka", "nasilsin"), ("teşekkürler", "tesekkur"),
    ("kimsin sen", "kimsin"), ("ne yapabilirsin", "yetenek"), ("bana bir şaka yap", "saka"),
    ("aferin", "iltifat"), ("görüşürüz", "veda"),
])
def test_sohbet(metin, niyet):
    r = anla(metin)
    assert r.tur == "sohbet" and r.niyet == niyet and r.komut is None


# ---------------------------------------------------------------------------
# Bağlam
# ---------------------------------------------------------------------------

class TestBaglam:

    def test_biraz_daha_ve_geri_al(self):
        b = Baglam()
        b.komut_calisti(SetVolume(delta=-15))
        assert anla("biraz daha", b).komut == SetVolume(delta=-15)
        assert anla("geri al", b).komut == SetVolume(delta=15)
        assert anla("fazla oldu", b).komut == SetVolume(delta=15)

    def test_biraz_daha_kis_bagламdan(self):
        b = Baglam()
        b.komut_calisti(SetBrightness(delta=10))
        assert anla("biraz daha kıs", b).komut == SetBrightness(delta=-10)

    def test_onu_kapat(self):
        b = Baglam()
        b.komut_calisti(OpenApplication(name="spotify"), "Spotify")
        assert anla("onu kapat", b).komut == CloseApplication(name="Spotify")

    def test_ne_dedin(self):
        b = Baglam()
        b.yanit_verildi("Pil yüzde 80.")
        assert anla("ne dedin", b).komut == Speak(text="Pil yüzde 80.")

    def test_tekrarlanacak_sey_yok(self):
        r = anla("biraz daha", Baglam())
        assert r.komut is None and r.kategori == "tekrar_yok"

    def test_baglam_zaman_asimi(self):
        t = [0.0]
        b = Baglam(ttl_saniye=60, clock=lambda: t[0])
        b.komut_calisti(SetVolume(delta=-15))
        t[0] = 61
        assert b.son_komut is None


def test_komut_kategorisi():
    assert komut_kategorisi(SetVolume(delta=-5)) == "ses_azaldi"
    assert komut_kategorisi(SetVolume(level=5)) == "ses_seviye"
    assert komut_kategorisi(MediaControl(action="next")) == "medya_sonraki"
    assert komut_kategorisi(GetBatteryStatus()) == "onay"


# ---------------------------------------------------------------------------
# Cevap şablonları
# ---------------------------------------------------------------------------

class TestYanitlar:

    def profil(self, *cumleler):
        a = UslupAnalizcisi()
        for c in cumleler:
            a.gozlemle(c)
        return a.profil()

    def test_agiz_secimi(self):
        assert agiz_sec(self.profil("ses kıs", "chrome aç")) == "kisa"
        assert agiz_sec(self.profil("Sesi kısar mısınız lütfen")) == "resmi"
        assert agiz_sec(self.profil("kanka şu sesi bi kıssana ya", "abi müziği açsana ya")) == "samimi"
        assert agiz_sec(UslupProfili()) == "notr"

    def test_hitap_aynalanir(self):
        y = YanitUretici(rng=random.Random(1))
        p = self.profil("reis şu sesi bi kıssana ya", "reis müziği de geçsene ya")
        metin = y.uret("ses_azaldi", p)
        assert "reis" in metin

    def test_resmi_efendim(self):
        y = YanitUretici(rng=random.Random(2))
        p = self.profil("Sesi kısar mısınız lütfen", "Teşekkür ederim")
        assert any(k in y.uret("ses_azaldi", p) for k in ("efendim", "düşürdüm"))

    def test_alanlar_ve_buyuk_harf(self):
        y = YanitUretici(rng=random.Random(3))
        metin = y.uret("uygulama_acildi", UslupProfili(), ad="spotify")
        assert metin[0].isupper() and "potify" in metin

    def test_ayni_cevap_ust_uste_gelmez(self):
        y = YanitUretici(rng=random.Random(4))
        p = UslupProfili()
        cevaplar = [y.uret("onay", p) for _ in range(6)]
        assert all(a != b for a, b in zip(cevaplar, cevaplar[1:]))

    def test_tum_kategoriler_her_agizda_uretilebilir(self):
        y = YanitUretici(kullanici_adi="Ata")
        for agiz_profili in (UslupProfili(samimiyet=0.9, hitap="abi"), UslupProfili(siz_hitabi=True),
                             UslupProfili(ortalama_kelime=2, sohbet_istegi=0.0), UslupProfili()):
            for k in YanitUretici.kategoriler():
                metin = y.uret(k, agiz_profili, ad="X", n=5, detay="bir sorun var")
                assert metin and "{" not in metin


# ---------------------------------------------------------------------------
# Uyandırma
# ---------------------------------------------------------------------------

class TestUyandirma:

    def test_kelimeyle_baslayan_islenir(self):
        u = UyandirmaFiltresi("irle", clock=lambda: 0.0)
        assert u.filtrele("İrle sesi kıs") == "sesi kıs"
        assert u.filtrele("hey irle, saat kaç") == "saat kaç"

    def test_stt_hatalari(self):
        for v in ("Erle sesi kıs", "ırle sesi kıs", "irla sesi kıs", "İrle'm sesi kıs"):
            u = UyandirmaFiltresi("irle", clock=lambda: 0.0)
            assert u.filtrele(v) == "sesi kıs", v

    def test_kelimesiz_yok_sayilir(self):
        u = UyandirmaFiltresi("irle", clock=lambda: 0.0)
        assert u.filtrele("televizyonda biri sesi kıs dedi") is None
        assert u.filtrele("ile birlikte geldik") is None   # "ile" yanlış alarm değil

    def test_sadece_isim(self):
        u = UyandirmaFiltresi("irle", clock=lambda: 0.0)
        assert u.filtrele("İrle") == ""

    def test_sohbet_penceresi(self):
        t = [0.0]
        u = UyandirmaFiltresi("irle", pencere_saniye=20, clock=lambda: t[0])
        u.filtrele("irle sesi kıs")
        t[0] = 10
        assert u.filtrele("biraz daha") == "biraz daha"
        t[0] = 40
        assert u.filtrele("biraz daha") is None


# ---------------------------------------------------------------------------
# Zamanlayıcı
# ---------------------------------------------------------------------------

class FakeTimer:
    created = []

    def __init__(self, delay, fn, args=()):
        self.delay, self.fn, self.args = delay, fn, args
        self.daemon = False
        self.started = self.cancelled = False
        FakeTimer.created.append(self)

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True

    def is_alive(self):
        return self.started and not self.cancelled

    def fire(self):
        self.fn(*self.args)


class TestTimerHandler:

    def setup_method(self):
        FakeTimer.created = []
        self.bus = MagicMock()
        self.dispatched = []
        from irle.adapters.intent.rule_engine import RuleEngine
        self.h = TimerHandler(self.bus, dispatch=self.dispatched.append, parse=RuleEngine().parse,
                              timer_factory=FakeTimer)

    def test_komut_zamanlanir(self):
        r = self.h.handle_schedule(ScheduleCommand(delay_seconds=300, inner_command_text="müziği durdur"))
        t = FakeTimer.created[0]
        assert t.delay == 300 and t.started and r["tur"] == "MediaControl"
        t.fire()
        assert self.dispatched == [MediaControl(action="play_pause")]

    def test_hatirlatma(self):
        self.h.handle_schedule(ScheduleCommand(delay_seconds=60, inner_command_text="çayı hatırlat"))
        FakeTimer.created[0].fire()
        assert self.dispatched == [Speak(text="Hatırlatma: çayı")]
        spoken = [c.args[0].text for c in self.bus.publish.call_args_list if isinstance(c.args[0], TtsRequested)]
        assert spoken[0] == "Tamam, 1 dakika sonra hatırlatacağım."

    def test_iptal(self):
        self.h.handle_schedule(ScheduleCommand(delay_seconds=60, inner_command_text="çay"))
        self.h.handle_schedule(ScheduleCommand(delay_seconds=90, inner_command_text="su"))
        assert self.h.active_count == 2
        assert self.h.handle_cancel_all(CancelAllTimers()) == {"iptal_edilen": 2}
        assert all(t.cancelled for t in FakeTimer.created)

    @pytest.mark.parametrize("delay", [0, -5, 999999])
    def test_gecersiz_sure(self, delay):
        with pytest.raises(ValueError):
            self.h.handle_schedule(ScheduleCommand(delay_seconds=delay, inner_command_text="x"))


# ---------------------------------------------------------------------------
# Pencere / süreç
# ---------------------------------------------------------------------------

class TestWindowHandler:

    def win(self, title):
        w = MagicMock()
        w.title = title
        return w

    def test_kucult_ilk_eslesen(self):
        api = MagicMock()
        a, b = self.win("Google Chrome - Sekme"), self.win("Not Defteri")
        api.getAllWindows.return_value = [a, b]
        WindowHandler(MagicMock(), windows_api=api).handle_window(WindowControl("chrome", "minimize"))
        a.minimize.assert_called_once()
        b.minimize.assert_not_called()

    def test_bulunamazsa_soyler(self):
        api = MagicMock()
        api.getAllWindows.return_value = []
        bus = MagicMock()
        r = WindowHandler(bus, windows_api=api).handle_window(WindowControl("x", "close"))
        assert r == {"bulunan": 0}

    def test_kill_sadece_eslesen_ve_korunan_degil(self):
        procs = []
        for name in ("Discord.exe", "discordhelper.exe", "chrome.exe", "svchost.exe"):
            p = MagicMock()
            p.info = {"pid": len(procs) + 100, "name": name}
            procs.append(p)
        ps = MagicMock()
        ps.process_iter.return_value = procs
        r = WindowHandler(MagicMock(), process_api=ps).handle_kill(KillProcess("discord"))
        assert r == {"sonlandirilan": 2}
        procs[2].kill.assert_not_called()
        procs[3].kill.assert_not_called()

    @pytest.mark.parametrize("ad", ["svchost", "lsass.exe", "ab"])
    def test_kill_korunan_veya_kisa_reddedilir(self, ad):
        with pytest.raises(ValueError):
            WindowHandler(MagicMock(), process_api=MagicMock()).handle_kill(KillProcess(ad))


# ---------------------------------------------------------------------------
# Yankı kilidi
# ---------------------------------------------------------------------------

class TestEchoGuard:

    def test_konusurken_ve_kuyrukta_aktif(self):
        t = [0.0]
        g = EchoGuard(tail_seconds=0.5, clock=lambda: t[0])
        assert not g.active
        g.started("merhaba")
        assert g.active
        t[0] = 2.0
        g.finished()
        assert g.active
        t[0] = 2.6
        assert not g.active

    def test_bos_metin_kilitlemez(self):
        g = EchoGuard()
        g.started("  ")
        assert not g.active

    def test_takili_kilit_kendini_acar(self):
        t = [0.0]
        g = EchoGuard(max_hold_seconds=30, clock=lambda: t[0])
        g.started("uzun konuşma")
        t[0] = 31
        assert not g.active


# ---------------------------------------------------------------------------
# IntentModulu — beyinsiz (köy modu) uçtan uca
# ---------------------------------------------------------------------------

class TestCevrimdisiAkis:

    def setup_method(self):
        from modules.intent_modulu import IntentModulu
        self.bus = TypedEventBus(max_workers=1)
        self.tts = []
        self.bus.subscribe(TtsRequested, lambda e: self.tts.append(e.text))
        self.cmd = CommandBus(self.bus)
        self.log = []
        self.cmd.register(SetVolume, self.log.append)                       # sessiz handler
        self.cmd.register(GetBatteryStatus, lambda q: self.bus.publish(TtsRequested(text="Pil yüzde 80.")))
        self.cmd.register(OpenApplication, self._fail_open)
        self.cmd.register(Speak, lambda c: self.bus.publish(TtsRequested(text=c.text)))
        self.IntentModulu = IntentModulu

    def _fail_open(self, cmd):
        raise FileNotFoundError(f"{cmd.name} uygulamasını bulamadım.")

    def teardown_method(self):
        self.bus.shutdown(wait=True)

    def run(self, *cumleler, settings=None):
        m = self.IntentModulu(self.bus, self.cmd, brain=None, settings=settings,
                              yanitlar=YanitUretici(rng=random.Random(0)))
        for c in cumleler:
            m._ses_islendi(SpeechRecognized(text=c))
        self.bus.shutdown(wait=True)
        return m

    def test_sessiz_handlera_uslupla_onay(self):
        self.run("kanka sesi kıs ya", "abi sesi bi kıssana ya")
        assert self.log == [SetVolume(delta=-15), SetVolume(delta=-15)]
        assert len(self.tts) == 2
        assert "abi" in self.tts[1].lower() or "kıstım" in self.tts[1].lower()

    def test_handler_sozu_aynen(self):
        self.run("pil ne durumda")
        assert self.tts == ["Pil yüzde 80."]

    def test_hata_dogru_soylenir(self):
        self.run("spotify'ı aç")
        assert len(self.tts) == 1 and "bulamadım" in self.tts[0]
        assert "açılıyor" not in self.tts[0]

    def test_sohbet_sablonu(self):
        self.run("teşekkürler")
        assert self.tts and self.tts[0]

    def test_baglam_uctan_uca(self):
        self.run("sesi kıs", "biraz daha", "geri al")
        assert self.log == [SetVolume(delta=-15), SetVolume(delta=-15), SetVolume(delta=15)]

    def test_ne_dedin_son_cevabi_tekrarlar(self):
        self.run("pil ne durumda", "ne dedin")
        assert self.tts == ["Pil yüzde 80.", "Pil yüzde 80."]

    def test_olumsuz_hicbir_sey_yapmaz(self):
        self.run("sesi kısma")
        assert self.log == [] and len(self.tts) == 1

    def test_uyandirma_kelimesi(self):
        class S:
            wake_word = "irle"
            wake_window = 0.0
            assistant_name = "İrle"
            user_name = ""
        self.run("sesi kıs", "İrle sesi kıs", settings=S())
        assert self.log == [SetVolume(delta=-15)]
