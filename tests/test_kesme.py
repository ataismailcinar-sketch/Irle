# -*- coding: utf-8 -*-
"""
=============================================================================
TEST — Konuşmayı yarıda kesme: karar, yankı ayrımı, TTS durdurma, uçtan uca
=============================================================================
"""

from __future__ import annotations

import sys
import threading
import time
import types
from types import SimpleNamespace

import pytest

from irle.adapters.intent.kesme import kesme_karari, yanki_mi
from irle.infra.kesme_dinleyici import KesmeDinleyici

SOYLENEN = ["Tamamdır kanka, sesi kıstım. Bugün hava çok güzel görünüyor, dışarı çıkmayı düşünür müsün?"]


# ---------------------------------------------------------------------------
# Karar
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("metin", ["dur", "Dur!", "sus artık", "yeter", "tamam tamam", "İrle dur",
                                   "irle sus lütfen", "bekle bir saniye", "kes artık", "sessiz ol"])
def test_dur(metin):
    assert kesme_karari(metin, SOYLENEN) == ("dur", None)


@pytest.mark.parametrize("metin", ["İrle sesi kıs", "İrle, spotify aç", "erle müziği durdur"])
def test_uyandirmali_komut(metin):
    assert kesme_karari(metin, SOYLENEN) == ("komut", metin)


@pytest.mark.parametrize("metin", [
    "bugün hava çok güzel",              # İrle'nin kendi sözü (yankı)
    "dışarı çıkmayı düşünür",
    "kanka sesi kıstım",
    "dur bakalım şu işe",                # uzun / belirsiz → kesme
    "duracak mısın acaba neden",
    "ilk önce", "", "   ",
])
def test_yok_say(metin):
    assert kesme_karari(metin, SOYLENEN) is None


def test_irle_dur_derken_duyulan_dur_yankidir():
    assert kesme_karari("dur", ["Dur, bir düşüneyim."]) is None


def test_yanki_mi():
    assert yanki_mi("sesi kıstım", SOYLENEN)
    assert yanki_mi("dışarı çıkmayı düşünür müsün", SOYLENEN)
    assert not yanki_mi("spotify aç", SOYLENEN)


# ---------------------------------------------------------------------------
# Kesme dinleyici (yankı mı kullanıcı mı?)
# ---------------------------------------------------------------------------

def besle(d, dizi):
    """dizi: (enerji, tts_seviyesi) çiftleri → dönen parçalar"""
    out = []
    for i, (e, sv) in enumerate(dizi):
        p = d.besle(f"b{i}", e, sv)
        if p:
            out.append(p)
    return out


class TestKesmeDinleyici:

    def test_sadece_yanki_gonderilmez(self):
        d = KesmeDinleyici(temel_esik=200, clock=lambda: 0.0)
        # İrle konuşurken mikrofon yüksek ama İrle hiç susmuyor → yankı
        assert besle(d, [(500, 0.9), (600, 0.8), (550, 0.7), (100, 0.6), (90, 0.5)]) == []

    def test_irle_susarken_ses_varsa_gonderilir(self):
        d = KesmeDinleyici(temel_esik=200, clock=lambda: 0.0)
        parcalar = besle(d, [(500, 0.9), (520, 0.05), (480, 0.8), (100, 0.6), (90, 0.5)])
        assert len(parcalar) == 1 and parcalar[0][:3] == ["b0", "b1", "b2"]

    def test_tek_blok_tikirti_gonderilmez(self):
        d = KesmeDinleyici(temel_esik=200, clock=lambda: 0.0)
        assert besle(d, [(900, 0.0), (50, 0.0), (50, 0.0)]) == []

    def test_windows_sesinde_yuksek_esik(self):
        d = KesmeDinleyici(temel_esik=200, clock=lambda: 0.0)
        assert besle(d, [(400, None), (420, None), (50, None), (50, None)]) == []      # orta → yankı say
        assert len(besle(d, [(700, None), (650, None), (50, None), (50, None)])) == 1  # çok yüksek → kullanıcı

    def test_iki_istek_arasi_bekleme(self):
        t = [0.0]
        d = KesmeDinleyici(temel_esik=200, min_aralik_saniye=2.0, clock=lambda: t[0])
        kul = [(500, 0.0), (500, 0.0), (50, 0.0), (50, 0.0)]
        assert len(besle(d, kul)) == 1
        t[0] = 1.0
        assert besle(d, kul) == []
        t[0] = 3.5
        assert len(besle(d, kul)) == 1

    def test_uzun_parca_kesilir(self):
        d = KesmeDinleyici(temel_esik=200, max_blok=4, clock=lambda: 0.0)
        parcalar = besle(d, [(500, 0.0)] * 4)
        assert len(parcalar) == 1 and len(parcalar[0]) == 4


# ---------------------------------------------------------------------------
# TTS durdurma
# ---------------------------------------------------------------------------

class TestTtsDurdurma:

    def test_piper_kalan_cumleleri_atlar(self):
        from irle.adapters.speech.tts_adapter import PiperTTS
        from irle.infra.ses_seviyesi import seviye_olcer

        class V:
            def synthesize(self, metin, syn_config=None):
                for c in metin.split("."):
                    yield SimpleNamespace(audio_int16_array=c, sample_rate=1)

        calinan, durduruldu = [], []
        tts = None

        def player(ses, hz):
            calinan.append(ses)
            if len(calinan) == 2:
                tts.durdur()          # 2. cümle çalarken kullanıcı "dur" dedi

        tts = PiperTTS("x", voice_loader=lambda y: V(), player=player, stopper=lambda: durduruldu.append(1))
        seviye_olcer.baslat([20000] * 1600, 16000)
        tts.konus("bir.iki.üç.dört")
        assert calinan == ["bir", "iki"] and durduruldu == [1]
        assert seviye_olcer.seviye() is None        # ağız hemen kapandı
        tts.konus("beş.altı")                        # sonraki konuşma normal
        assert calinan[-2:] == ["beş", "altı"]

    def test_tts_modulu_kuyrugu_bosaltir_ve_dengeyi_korur(self, monkeypatch):
        import modules.tts_modulu as tm
        from irle.infra.event_bus import TypedEventBus

        basladi = threading.Event()
        birak = threading.Event()
        soylenen = []

        class Motor:
            name = "sahte"
            def konus(self, m):
                soylenen.append(m)
                basladi.set()
                birak.wait(2)
            def durdur(self):
                birak.set()

        monkeypatch.setattr(tm, "ses_motoru_kur", lambda **k: Motor())
        bus = TypedEventBus(max_workers=2)
        bitenler = []
        bus.subscribe("tts_bitti", lambda m: bitenler.append(m["data"]["metin"]))
        mod = tm.TtsModulu(bus, SimpleNamespace(tts_engine="auto", piper_voice="", piper_speed=1.0,
                                                 tts_voice_name=""))
        mod.baslat()
        for m in ("bir", "iki", "üç"):
            mod._konusma_istegi_alindi({"data": {"metin": m}})
        assert basladi.wait(2)
        mod._kes({"data": {}})
        t0 = time.time()
        while len(bitenler) < 3 and time.time() - t0 < 2:
            time.sleep(0.01)
        assert soylenen == ["bir"]                       # iki ve üç hiç söylenmedi
        assert sorted(bitenler) == sorted(["bir", "iki", "üç"])   # yankı kilidi sayacı dengede
        mod.durdur(); bus.shutdown()


# ---------------------------------------------------------------------------
# Ses modülü — kesme kararı uçtan uca
# ---------------------------------------------------------------------------

@pytest.fixture
def ses_modulu(monkeypatch):
    sd = types.ModuleType("sounddevice")
    sd.InputStream = object
    monkeypatch.setitem(sys.modules, "sounddevice", sd)
    sys.modules.pop("modules.ses_modulu", None)
    import modules.ses_modulu as sm
    return sm


class FakeBus:
    def __init__(self):
        self.yayinlanan = []

    def subscribe(self, *a):
        pass

    def publish(self, e, data=None):
        self.yayinlanan.append(e if data is None else (e, data))


@pytest.mark.parametrize("duyulan,beklenen", [
    ("dur", ["konusmayi_kes"]),
    ("İrle sesi kıs", ["konusmayi_kes", "SpeechRecognized:İrle sesi kıs"]),
    ("sesi kıstım", []),                 # yankı
    (None, []),                          # gürültü
])
def test_kesme_cozumle(ses_modulu, duyulan, beklenen):
    bus = FakeBus()

    class STT:
        def transcribe(self, *a, **k):
            return duyulan

    m = ses_modulu.SesModulu(bus, stt_provider=STT())
    m._soylenenler.append("Tamamdır kanka, sesi kıstım.")
    m._kesme_cozumle(b"\x00\x00")
    ozet = []
    for e in bus.yayinlanan:
        if isinstance(e, tuple):
            ozet.append(e[0])
        else:
            ozet.append(f"{type(e).__name__}:{e.text}")
    assert ozet == beklenen
