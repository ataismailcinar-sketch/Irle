# -*- coding: utf-8 -*-
"""
=============================================================================
TEST — Hibrit kulak: Groq Whisper, yerel Whisper, halüsinasyon süzgeci, fabrika
=============================================================================
Ağ ve gerçek model YOK: hepsi sahte transport / sahte model ile.
"""

from __future__ import annotations

import io
import wave
from types import SimpleNamespace

import pytest

from irle.adapters.speech import stt_adapter as stt
from irle.adapters.speech.stt_adapter import (
    GroqWhisperSTT, HybridSTT, LocalWhisperSTT, STTUnavailable, halusinasyon_mu,
)

SES = (b"\x10\x00\xf0\xff" * 4000)  # 0.5 sn 16 kHz int16 "ses"


# ---------------------------------------------------------------------------
# Halüsinasyon süzgeci
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("metin", [
    "Altyazı M.K.", "altyazı", "İzlediğiniz için teşekkür ederim.", "Abone olmayı unutmayın!",
    "[Müzik]", "...", "", "   ",
    "Teşekkürler. Teşekkürler. Teşekkürler. Teşekkürler. Teşekkürler. Teşekkürler.",
])
def test_halusinasyonlar_suzulur(metin):
    assert halusinasyon_mu(metin)


@pytest.mark.parametrize("metin", [
    "sesi kıs", "Teşekkürler", "İrle spotify'ı aç", "yarın saat onda toplantı var diye not al",
])
def test_gercek_konusma_gecer(metin):
    assert not halusinasyon_mu(metin)


def test_segment_suzgeci_sessiz_segmenti_atar():
    segs = [
        {"text": " sesi kıs", "no_speech_prob": 0.05, "avg_logprob": -0.2},
        {"text": " Altyazı M.K.", "no_speech_prob": 0.1, "avg_logprob": -0.3},
        {"text": " hmm", "no_speech_prob": 0.9, "avg_logprob": -1.5},
    ]
    assert stt._segmentleri_suz(segs) == "sesi kıs"
    nesneler = [SimpleNamespace(**s) for s in segs]
    assert stt._segmentleri_suz(nesneler) == "sesi kıs"


# ---------------------------------------------------------------------------
# Groq Whisper
# ---------------------------------------------------------------------------

class TestGroqWhisper:

    def test_istek_bicimi_ve_cevap(self):
        yakalanan = {}

        def transport(url, govde, headers, timeout):
            yakalanan.update(url=url, govde=govde, headers=headers)
            return {"text": "sesi kıs", "segments": [
                {"text": "sesi kıs", "no_speech_prob": 0.01, "avg_logprob": -0.1}]}

        g = GroqWhisperSTT("gsk_x", transport=transport)
        assert g.transcribe(SES, language="tr-TR") == "sesi kıs"
        assert yakalanan["url"] == "https://api.groq.com/openai/v1/audio/transcriptions"
        assert yakalanan["headers"]["Authorization"] == "Bearer gsk_x"
        sinir = yakalanan["headers"]["Content-Type"].split("boundary=")[1]
        govde = yakalanan["govde"]
        assert f"--{sinir}--".encode() in govde
        for alan, deger in (("model", "whisper-large-v3-turbo"), ("language", "tr"),
                            ("response_format", "verbose_json")):
            assert f'name="{alan}"\r\n\r\n{deger}\r\n'.encode() in govde
        # gönderilen dosya geçerli bir WAV mı?
        wav = govde.split(b"Content-Type: audio/wav\r\n\r\n", 1)[1].rsplit(f"\r\n--{sinir}--".encode(), 1)[0]
        with wave.open(io.BytesIO(wav)) as w:
            assert (w.getnchannels(), w.getframerate(), w.getsampwidth()) == (1, 16000, 2)
            assert w.getnframes() == len(SES) // 2

    def test_halusinasyon_none(self):
        g = GroqWhisperSTT("k", transport=lambda *a: {"text": "Altyazı M.K."})
        assert g.transcribe(SES) is None

    def test_anahtarsiz_olmaz(self):
        with pytest.raises(ValueError):
            GroqWhisperSTT("")

    def test_ag_hatasi_unavailable(self):
        with pytest.raises(STTUnavailable):
            stt._post_multipart("http://127.0.0.1:9/x", b"", {}, 1)


# ---------------------------------------------------------------------------
# Yerel Whisper
# ---------------------------------------------------------------------------

class FakeModel:
    def __init__(self, metin="sesi kıs", hata=None):
        self.metin, self.hata, self.cagri = metin, hata, []

    def transcribe(self, ses, **kw):
        self.cagri.append(kw)
        if self.hata:
            raise self.hata
        return iter([SimpleNamespace(text=self.metin, no_speech_prob=0.0, avg_logprob=-0.1)]), None


class TestLocalWhisper:

    def test_cuda_yoksa_cpu(self):
        yuklenen = []

        def factory(model, device, compute_type):
            yuklenen.append((device, compute_type))
            if device == "cuda":
                raise RuntimeError("CUDA driver not found")
            return FakeModel()

        w = LocalWhisperSTT("small", device="auto", model_factory=factory)
        assert w.transcribe(SES) == "sesi kıs"
        assert yuklenen == [("cuda", "int8_float16"), ("cpu", "int8")]

    def test_ilk_tanimada_cublas_hatasi_cpuya_gecer(self):
        modeller = {"cuda": FakeModel(hata=RuntimeError("Library cublas64_12.dll is not found")),
                    "cpu": FakeModel("müziği durdur")}
        w = LocalWhisperSTT(model_factory=lambda m, device, compute_type: modeller[device])
        assert w.transcribe(SES) == "müziği durdur"
        assert w._aktif_cihaz == "cpu"

    def test_parametreler(self):
        m = FakeModel()
        w = LocalWhisperSTT(device="cpu", model_factory=lambda *a, **k: m)
        w.transcribe(SES, language="tr-TR")
        kw = m.cagri[0]
        assert kw["language"] == "tr" and kw["vad_filter"] is True
        assert kw["condition_on_previous_text"] is False

    def test_kurulu_degilse_unavailable(self):
        def factory(*a, **k):
            raise ImportError("No module named faster_whisper")
        w = LocalWhisperSTT(model_factory=factory)
        with pytest.raises(STTUnavailable):
            w.transcribe(SES)
        assert not w.hazirla()   # tekrar denemez

    def test_halusinasyon_none(self):
        w = LocalWhisperSTT(device="cpu", model_factory=lambda *a, **k: FakeModel("Altyazı M.K."))
        assert w.transcribe(SES) is None


# ---------------------------------------------------------------------------
# Hibrit
# ---------------------------------------------------------------------------

class P:
    def __init__(self, name, sonuc=None, hata=None):
        self.name, self.sonuc, self.hata, self.n = name, sonuc, hata, 0

    def transcribe(self, *a, **k):
        self.n += 1
        if self.hata:
            raise self.hata
        return self.sonuc


class TestHybrid:

    def test_konusma_yoksa_digerine_sormaz(self):
        a, b = P("groq", None), P("yerel", "metin")
        h = HybridSTT([a, b])
        assert h.transcribe(SES) is None
        assert (a.n, b.n) == (1, 0)

    def test_calismayan_atlanir_ve_dinlenir(self):
        t = [0.0]
        a, b = P("groq", hata=STTUnavailable("internet yok")), P("yerel", "sesi kıs")
        h = HybridSTT([a, b], cooldown_seconds=60, clock=lambda: t[0])
        assert h.transcribe(SES) == "sesi kıs" and h.last_provider == "yerel"
        h.transcribe(SES)
        assert a.n == 1                      # dinlenmede, denenmedi
        t[0] = 61
        h.transcribe(SES)
        assert a.n == 2

    def test_hepsi_dusse_none(self):
        h = HybridSTT([P("a", hata=STTUnavailable("x")), P("b", hata=RuntimeError("y"))])
        assert h.transcribe(SES) is None


# ---------------------------------------------------------------------------
# Fabrika
# ---------------------------------------------------------------------------

class TestFabrika:

    @pytest.fixture(autouse=True)
    def _yamalar(self, monkeypatch):
        import irle.app.stt_factory as f
        monkeypatch.setattr(f, "_google", lambda: P("google"))
        monkeypatch.setattr(f, "_faster_whisper_var", lambda: True)
        self.f = f

    def ayar(self, mode, key="k"):
        return SimpleNamespace(stt_mode=mode, groq_api_key=key, groq_stt_model="whisper-large-v3-turbo",
                               whisper_model="small", whisper_device="cpu")

    @pytest.mark.parametrize("mode,key,beklenen", [
        ("hibrit", "k", ["groq-whisper", "yerel-whisper", "google"]),
        ("hibrit", "", ["yerel-whisper", "google"]),
        ("yerel", "k", ["yerel-whisper"]),
        ("groq", "k", ["groq-whisper", "google"]),
        ("google", "k", ["google"]),
    ])
    def test_modlar(self, mode, key, beklenen):
        assert self.f.build_stt(self.ayar(mode, key), preload=False).providers == beklenen

    def test_faster_whisper_yoksa_hibrit_yine_calisir(self, monkeypatch):
        monkeypatch.setattr(self.f, "_faster_whisper_var", lambda: False)
        assert self.f.build_stt(self.ayar("hibrit", ""), preload=False).providers == ["google"]
