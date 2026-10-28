# -*- coding: utf-8 -*-
"""
=============================================================================
TEST — Ses (TTS): metin hazırlama, Piper, Windows sesi, motor seçimi, TtsModulu
=============================================================================
Gerçek ses kartı / model YOK: hepsi sahte nesnelerle.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from irle.adapters.speech import tts_adapter as ta
from irle.adapters.speech.tts_adapter import (
    PiperTTS, Pyttsx3TTS, metni_hazirla, piper_modeli_bul, ses_motoru_kur, turkce_ses_mi,
)


# ---------------------------------------------------------------------------
# Metin hazırlama
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("girdi,cikti", [
    ("Pil %73", "Pil yüzde 73"),
    ("Pil 73%", "Pil yüzde 73"),
    ("Saat 12:08", "Saat 12 8"),
    ("Saat 09:00", "Saat 9"),
    ("**Tamam** abi 😀", "Tamam abi"),
    ("Şuraya bak: https://example.com tamam", "Şuraya bak: tamam"),
    ("Disk 12.5 GB boş", "Disk 12 nokta 5 gigabayt boş"),
    ("```print(1)``` bitti", "bitti"),
    ("", ""),
])
def test_metni_hazirla(girdi, cikti):
    assert metni_hazirla(girdi) == cikti


# ---------------------------------------------------------------------------
# Piper model bulma
# ---------------------------------------------------------------------------

def _ses_dosyasi(dizin, ad):
    (dizin / f"{ad}.onnx").write_bytes(b"x")
    (dizin / f"{ad}.onnx.json").write_text("{}")


class TestPiperModeliBul:

    def test_yoksa_none(self, tmp_path):
        assert piper_modeli_bul("", str(tmp_path)) is None

    def test_json_yoksa_sayilmaz(self, tmp_path):
        (tmp_path / "tr_TR-fahrettin-medium.onnx").write_bytes(b"x")
        assert piper_modeli_bul("", str(tmp_path)) is None

    def test_varsayilan_sira(self, tmp_path):
        _ses_dosyasi(tmp_path, "tr_TR-dfki-medium")
        _ses_dosyasi(tmp_path, "tr_TR-fahrettin-medium")
        assert piper_modeli_bul("", str(tmp_path)).endswith("tr_TR-fahrettin-medium.onnx")

    def test_tercih(self, tmp_path):
        _ses_dosyasi(tmp_path, "tr_TR-dfki-medium")
        _ses_dosyasi(tmp_path, "tr_TR-fahrettin-medium")
        assert piper_modeli_bul("tr_TR-dfki-medium", str(tmp_path)).endswith("dfki-medium.onnx")

    def test_baska_turkce_ses(self, tmp_path):
        _ses_dosyasi(tmp_path, "tr_TR-yeni-high")
        assert piper_modeli_bul("", str(tmp_path)).endswith("tr_TR-yeni-high.onnx")

    def test_tam_yol(self, tmp_path):
        _ses_dosyasi(tmp_path, "benim")
        yol = str(tmp_path / "benim.onnx")
        assert piper_modeli_bul(yol, str(tmp_path / "yok")) == yol


# ---------------------------------------------------------------------------
# Piper
# ---------------------------------------------------------------------------

class FakeVoice:
    def __init__(self):
        self.cagri = []

    def synthesize(self, metin, syn_config=None):
        self.cagri.append((metin, syn_config))
        for cumle in metin.split(". "):
            yield SimpleNamespace(audio_int16_array=[len(cumle)], sample_rate=22050)


def test_piper_cumle_cumle_calar():
    voice = FakeVoice()
    calinan = []
    tts = PiperTTS("x.onnx", hiz=1.25, voice_loader=lambda yol: voice,
                   player=lambda ses, hz: calinan.append((ses, hz)))
    tts.konus("Merhaba. Sesi kıstım")
    assert calinan == [([7], 22050), ([11], 22050)]
    cfg = voice.cagri[0][1]
    assert cfg is not None and abs(cfg.length_scale - 0.8) < 1e-6   # hız 1.25 → length_scale 0.8


# ---------------------------------------------------------------------------
# Windows sesi
# ---------------------------------------------------------------------------

class FakeEngine:
    def __init__(self, sesler):
        self.props = {"voices": sesler}
        self.soylenen = []

    def setProperty(self, k, v):
        self.props[k] = v

    def getProperty(self, k):
        return self.props.get(k)

    def say(self, m):
        self.soylenen.append(m)

    def runAndWait(self):
        pass


def ses(name, id_="x", languages=()):
    return SimpleNamespace(name=name, id=id_, languages=list(languages))


class TestWindowsSesi:

    def test_turkce_ses_tespiti(self):
        assert turkce_ses_mi(ses("Microsoft Tolga Desktop - Turkish"))
        assert turkce_ses_mi(ses("X", languages=[b"\x05tr-TR"]))
        assert not turkce_ses_mi(ses("Microsoft David Desktop - English (United States)"))

    def test_turkce_ses_otomatik_secilir(self):
        e = FakeEngine([ses("David", "D"), ses("Microsoft Tolga - Turkish", "T")])
        Pyttsx3TTS(engine_factory=lambda: e).konus("merhaba")
        assert e.props["voice"] == "T" and e.soylenen == ["merhaba"]

    def test_ad_verilirse_o_secilir(self):
        e = FakeEngine([ses("Zira", "Z"), ses("Tolga Turkish", "T")])
        Pyttsx3TTS(ses_adi="zira", engine_factory=lambda: e)
        assert e.props["voice"] == "Z"


# ---------------------------------------------------------------------------
# Motor seçimi
# ---------------------------------------------------------------------------

class TestMotorSecimi:

    @pytest.fixture(autouse=True)
    def _sahte(self, monkeypatch):
        self.olusan = []

        class P:
            name = "piper"
            def __init__(s, yol, **k):
                self.olusan.append(("piper", yol))

        class W:
            name = "pyttsx3"
            def __init__(s, **k):
                self.olusan.append(("pyttsx3", None))

        monkeypatch.setattr(ta, "PiperTTS", P)
        monkeypatch.setattr(ta, "Pyttsx3TTS", W)

    def test_auto_ses_varsa_piper(self, monkeypatch):
        monkeypatch.setattr(ta, "piper_modeli_bul", lambda tercih: "data/sesler/tr.onnx")
        assert ses_motoru_kur("auto").name == "piper"

    def test_auto_ses_yoksa_windows(self, monkeypatch):
        monkeypatch.setattr(ta, "piper_modeli_bul", lambda tercih: None)
        assert ses_motoru_kur("auto").name == "pyttsx3"

    def test_piper_hata_verirse_windows(self, monkeypatch):
        monkeypatch.setattr(ta, "piper_modeli_bul", lambda tercih: "x.onnx")

        def patla(*a, **k):
            raise ImportError("piper yok")
        monkeypatch.setattr(ta, "PiperTTS", patla)
        assert ses_motoru_kur("auto").name == "pyttsx3"

    def test_pyttsx3_zorla(self, monkeypatch):
        monkeypatch.setattr(ta, "piper_modeli_bul", lambda tercih: "x.onnx")
        assert ses_motoru_kur("pyttsx3").name == "pyttsx3"


# ---------------------------------------------------------------------------
# TtsModulu
# ---------------------------------------------------------------------------

class TestTtsModulu:

    def kur(self, monkeypatch, motor):
        import modules.tts_modulu as tm
        from irle.infra.event_bus import TypedEventBus
        monkeypatch.setattr(tm, "ses_motoru_kur", lambda **k: motor)
        bus = TypedEventBus(max_workers=2)
        bitenler = []
        bus.subscribe("tts_bitti", lambda m: bitenler.append(m["data"]["metin"]))
        ayar = SimpleNamespace(tts_engine="auto", piper_voice="", piper_speed=1.0, tts_voice_name="")
        mod = tm.TtsModulu(bus, ayar)
        mod.baslat()
        return bus, mod, bitenler

    def bekle(self, kosul, sure=2.0):
        t0 = time.time()
        while not kosul() and time.time() - t0 < sure:
            time.sleep(0.01)

    def test_konusur_ve_bitti_yayinlar(self, monkeypatch):
        soylenen = []
        motor = SimpleNamespace(name="sahte", konus=soylenen.append)
        bus, mod, bitenler = self.kur(monkeypatch, motor)
        bus.publish("tts_konuş", {"metin": "Pil %80"})
        self.bekle(lambda: bitenler)
        assert soylenen == ["Pil yüzde 80"] and bitenler == ["Pil %80"]
        mod.durdur(); bus.shutdown()

    def test_hata_olsa_da_bitti_yayinlar(self, monkeypatch):
        def patla(m):
            raise RuntimeError("ses kartı yok")
        bus, mod, bitenler = self.kur(monkeypatch, SimpleNamespace(name="sahte", konus=patla))
        bus.publish("tts_konuş", {"metin": "merhaba"})
        self.bekle(lambda: bitenler)
        assert bitenler == ["merhaba"]     # yankı kilidi takılı kalmaz
        mod.durdur(); bus.shutdown()

    def test_sessiz_mod(self, monkeypatch):
        import config
        soylenen = []
        bus, mod, bitenler = self.kur(monkeypatch, SimpleNamespace(name="sahte", konus=soylenen.append))
        monkeypatch.setattr(config, "SESSİZ_MOD", True, raising=False)
        bus.publish("tts_konuş", {"metin": "sessiz"})
        self.bekle(lambda: bitenler)
        assert soylenen == [] and bitenler == ["sessiz"]
        mod.durdur(); bus.shutdown()
