# -*- coding: utf-8 -*-
"""
=============================================================================
TEST — Hibrit Beyin (LLM istemcisi, araçlar, üslup, BrainService, Intent)
=============================================================================
Ağ YOK: tüm dil modeli cevapları sahte (fake) istemcilerle üretilir.
"""

from __future__ import annotations

import json
import os
import time

import pytest

from irle.adapters.brain import tools
from irle.adapters.brain.llm_client import (
    HybridLLMClient, LLMError, LLMReply, OpenAICompatClient, ToolCall,
)
from irle.adapters.brain.persona import UslupAnalizcisi, sistem_talimati
from irle.app.brain_service import BrainService
from irle.app.settings import Settings, load_dotenv
from irle.domain.commands import (
    CreateNote, DeleteNote, MediaControl, OpenApplication, SetVolume, ShutdownComputer, Speak,
)
from irle.domain.events import CommandFailed, Notification, SpeechRecognized, TtsRequested
from irle.domain.queries import GetBatteryStatus, ListNotes
from irle.infra.command_bus import CommandBus
from irle.infra.event_bus import TypedEventBus
from irle.infra.speech_capture import capture_speech


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------

class ScriptedLLM:
    """Sırayla önceden yazılmış cevapları döndüren sahte model."""

    name = "sahte"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, messages, tools_=None):
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools_})
        if not self.replies:
            return LLMReply(text="(bitti)", provider=self.name)
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class FailingLLM:
    def __init__(self, name):
        self.name = name
        self.count = 0

    def chat(self, messages, tools_=None):
        self.count += 1
        raise LLMError(f"{self.name} ulaşılamadı")


class RecordingBus:
    """TypedEventBus yerine — publish'leri kaydeder, yakalamaya saygı duyar."""

    def __init__(self):
        self.real = TypedEventBus(max_workers=1)
        self.tts = []
        self.real.subscribe(TtsRequested, lambda e: self.tts.append(e.text))

    def publish(self, e, data=None):
        self.real.publish(e, data)

    def subscribe(self, t, h):
        self.real.subscribe(t, h)

    def flush(self):
        self.real.shutdown(wait=True)


from irle.adapters.intent import yanitlar as _yanitlar
ANLAMADIM = {v.replace("{h}", "") for vs in _yanitlar._S["anlamadim"].values() for v in vs}


def call(name, **args):
    return ToolCall(id=f"id_{name}", name=name, arguments=args)


def make_cmd_bus(event_bus):
    """Gerçek CommandBus + OS'a dokunmayan sahte handler'lar."""
    bus = CommandBus(event_bus)
    log = []

    def vol(cmd):
        log.append(cmd)
        event_bus.publish(TtsRequested(text=f"Ses ayarlandı {cmd.delta or cmd.level}"))

    def batt(q):
        log.append(q)
        event_bus.publish(TtsRequested(text="Pil yüzdesi 80, şarjda."))
        return {"percent": 80, "plugged": True}

    def note(cmd):
        log.append(cmd)
        event_bus.publish(Notification(title="Notlar", message=f"Not alındı: {cmd.text}"))

    def boom(cmd):
        raise RuntimeError("pyautogui yok")

    bus.register(SetVolume, vol)
    bus.register(GetBatteryStatus, batt)
    bus.register(CreateNote, note)
    bus.register(MediaControl, boom)
    bus.register(ShutdownComputer, lambda c: log.append(c))
    bus.register(OpenApplication, lambda c: log.append(c))
    bus.register(Speak, lambda c: event_bus.publish(TtsRequested(text=c.text)))
    return bus, log


# ---------------------------------------------------------------------------
# OpenAICompatClient — cevap çözümleme
# ---------------------------------------------------------------------------

class TestOpenAICompatClient:

    def test_metin_cevabi(self):
        def transport(url, payload, headers, timeout):
            assert url == "http://x/v1/chat/completions"
            assert payload["model"] == "m"
            assert "Authorization" not in headers
            return {"choices": [{"message": {"content": "Merhaba!"}}]}

        c = OpenAICompatClient("t", "http://x/v1/", "m", transport=transport)
        r = c.chat([{"role": "user", "content": "selam"}])
        assert r.text == "Merhaba!" and r.tool_calls == ()

    def test_arac_cagrisi_string_argumanlar(self):
        def transport(url, payload, headers, timeout):
            assert headers["Authorization"] == "Bearer k"
            assert payload["tools"] and payload["tool_choice"] == "auto"
            return {"choices": [{"message": {"content": None, "tool_calls": [
                {"id": "a1", "type": "function",
                 "function": {"name": "ses_ayarla", "arguments": '{"degisim": -10}'}}]}}]}

        c = OpenAICompatClient("t", "http://x", "m", api_key="k", transport=transport)
        r = c.chat([], tools=[{"x": 1}])
        assert r.tool_calls[0] == ToolCall("a1", "ses_ayarla", {"degisim": -10})

    def test_ollama_dict_argumanlar_ve_think_blogu(self):
        def transport(*a):
            return {"choices": [{"message": {
                "content": "<think>düşünüyorum</think>Tamam abi.",
                "tool_calls": [{"function": {"name": "pil_durumu", "arguments": {}}}]}}]}

        r = OpenAICompatClient("o", "http://x", "m", transport=transport).chat([])
        assert r.text == "Tamam abi."
        assert r.tool_calls[0].name == "pil_durumu" and r.tool_calls[0].id == "call_0"

    def test_bozuk_cevap_llmerror(self):
        c = OpenAICompatClient("t", "http://x", "m", transport=lambda *a: {"error": "x"})
        with pytest.raises(LLMError):
            c.chat([])

    def test_gercek_ag_hatasi_llmerror(self):
        # Kapalı bir porta bağlanmaya çalış → URLError → LLMError
        c = OpenAICompatClient("t", "http://127.0.0.1:9", "m", timeout=1)
        with pytest.raises(LLMError):
            c.chat([{"role": "user", "content": "x"}])


# ---------------------------------------------------------------------------
# HybridLLMClient — yedeğe geçiş
# ---------------------------------------------------------------------------

class TestHybrid:

    def test_bulut_duserse_yerel(self):
        cloud = FailingLLM("groq")
        local = ScriptedLLM([LLMReply(text="yerelden", provider="ollama")])
        h = HybridLLMClient([cloud, local])
        assert h.chat([]).text == "yerelden"
        assert h.last_provider == "sahte"

    def test_dusen_saglayici_dinlenmeye_alinir(self):
        t = [0.0]
        cloud = FailingLLM("groq")
        local = ScriptedLLM([LLMReply(text="1"), LLMReply(text="2"), LLMReply(text="3")])
        h = HybridLLMClient([cloud, local], cooldown_seconds=60, clock=lambda: t[0])
        h.chat([]); h.chat([])
        assert cloud.count == 1          # ikinci istekte bulut hiç denenmedi
        t[0] = 61
        h.chat([])
        assert cloud.count == 2          # süre dolunca tekrar denendi

    def test_tek_seferlik_hata_dinlenmeye_almaz(self):
        class Flaky:
            name = "groq"
            count = 0
            def chat(self, m, t=None):
                Flaky.count += 1
                if Flaky.count == 1:
                    raise LLMError("HTTP 400: tool_use_failed", cooldown=False)
                return LLMReply(text="bulut")
        local = ScriptedLLM([LLMReply(text="yerel")])
        h = HybridLLMClient([Flaky(), local])
        assert h.chat([]).text == "yerel"
        assert h.chat([]).text == "bulut"   # bulut hemen tekrar denendi

    def test_hepsi_duserse_llmerror(self):
        h = HybridLLMClient([FailingLLM("a"), FailingLLM("b")])
        with pytest.raises(LLMError) as e:
            h.chat([])
        assert "a" in str(e.value) and "b" in str(e.value)

    def test_bos_liste_hata(self):
        with pytest.raises(ValueError):
            HybridLLMClient([])


# ---------------------------------------------------------------------------
# Araçlar
# ---------------------------------------------------------------------------

class TestTools:

    def test_her_aracin_semasi_gecerli(self):
        specs = tools.tool_specs()
        assert len(specs) == len(set(tools.tool_names())) >= 20
        for s in specs:
            assert s["type"] == "function"
            assert s["function"]["parameters"]["type"] == "object"
            json.dumps(s)  # JSON'a çevrilebilmeli

    @pytest.mark.parametrize("name,args,expected", [
        ("ses_ayarla", {"degisim": -10}, SetVolume(delta=-10)),
        ("ses_ayarla", {"seviye": 150}, SetVolume(level=100)),
        ("ses_ayarla", {"seviye": "40"}, SetVolume(level=40)),
        ("uygulama_ac", {"ad": "spotify"}, OpenApplication(name="spotify")),
        ("medya_kontrol", {"islem": "sonraki"}, MediaControl(action="next")),
        ("not_al", {"metin": "süt al"}, CreateNote(text="süt al")),
        ("not_sil", {"kapsam": "hepsi"}, DeleteNote(mode="all")),
        ("notlari_oku", {}, ListNotes(limit=3)),
        ("pil_durumu", {}, GetBatteryStatus()),
        ("bilgisayari_kapat", {}, ShutdownComputer(delay_seconds=60)),
    ])
    def test_build_command(self, name, args, expected):
        assert tools.build_command(name, args) == expected

    @pytest.mark.parametrize("name,args", [
        ("yok_boyle_arac", {}),
        ("ses_ayarla", {}),
        ("uygulama_ac", {"ad": "  "}),
        ("medya_kontrol", {"islem": "uç"}),
    ])
    def test_gecersiz(self, name, args):
        with pytest.raises(ValueError):
            tools.build_command(name, args)

    def test_tehlikeli_isaretli(self):
        assert tools.is_dangerous("bilgisayari_kapat")
        assert not tools.is_dangerous("ses_ayarla")


# ---------------------------------------------------------------------------
# Üslup analizi
# ---------------------------------------------------------------------------

class TestUslup:

    def profil(self, *cumleler):
        a = UslupAnalizcisi()
        for c in cumleler:
            a.gozlemle(c)
        return a.profil()

    def test_kanka(self):
        p = self.profil("kanka şu sesi kıs ya", "abi müziği aç bi")
        assert p.samimiyet > 0.65 and not p.siz_hitabi
        assert "samimi" in p.etiket()

    def test_resmi_siz(self):
        p = self.profil("Sesi kısar mısınız lütfen", "Teşekkür ederim, notlarımı okuyabilir misiniz?")
        assert p.siz_hitabi
        assert "resmî" in p.etiket()

    def test_kisa_net(self):
        p = self.profil("ses kıs", "chrome aç", "saat")
        assert p.kisa_ve_net

    def test_gergin(self):
        p = self.profil("of yeter ya yine çalışmıyor bu!")
        assert p.sabirsizlik > 0.4

    def test_sakaci(self):
        p = self.profil("hahaha çok iyiydi", "xd")
        assert p.espri > 0.3

    def test_yeni_cumleler_daha_agir(self):
        a = UslupAnalizcisi()
        for c in ["Sesi açar mısınız lütfen", "kanka naber ya", "abi bi müzik aç ya kanka"]:
            a.gozlemle(c)
        assert not a.profil().siz_hitabi

    def test_talimat_uslubu_yansitir(self):
        a = UslupAnalizcisi()
        a.gozlemle("Notlarımı okur musunuz lütfen")
        t = sistem_talimati(a.profil(), a.gozlem_sayisi, kullanici_adi="Ata", beyin="groq")
        assert "Siz" in t and "Ata" in t and "groq" in t
        a.sifirla()
        for c in ["kanka", "abi ya", "ses kıs"]:
            a.gozlemle(c)
        t2 = sistem_talimati(a.profil(), a.gozlem_sayisi)
        assert "Kanka gibi" in t2

    def test_ilk_karsilasma(self):
        t = sistem_talimati(UslupAnalizcisi().profil(), 0)
        assert "henüz tanımıyorsun" in t


# ---------------------------------------------------------------------------
# Konuşma yakalama
# ---------------------------------------------------------------------------

class TestSpeechCapture:

    def test_yakalanan_tts_sese_gitmez(self):
        rb = RecordingBus()
        with capture_speech() as cap:
            rb.publish(TtsRequested(text="gizli"))
            rb.publish(Notification(message="bildirim"))
            rb.publish(CommandFailed(command_type="X", error="patladı"))
        rb.publish(TtsRequested(text="açık"))
        rb.flush()
        assert cap.texts == ["gizli"]
        assert cap.notifications == ["bildirim"]
        assert cap.errors == ["patladı"]
        assert rb.tts == ["açık"]


# ---------------------------------------------------------------------------
# BrainService — uçtan uca
# ---------------------------------------------------------------------------

class TestBrainService:

    def setup_method(self):
        self.rb = RecordingBus()
        self.cmd_bus, self.log = make_cmd_bus(self.rb)

    def teardown_method(self):
        self.rb.flush()

    def test_sohbet_arac_yok(self):
        llm = ScriptedLLM([LLMReply(text="İyiyim kanka, sen?")])
        b = BrainService(llm, self.cmd_bus)
        r = b.handle("kanka naber")
        assert r.reply == "İyiyim kanka, sen?" and r.executed == ()
        assert llm.calls[0]["tools"]  # araçlar modele verildi

    def test_birden_fazla_arac_ve_gozlem(self):
        llm = ScriptedLLM([
            LLMReply(tool_calls=(call("ses_ayarla", degisim=-10), call("pil_durumu"))),
            LLMReply(text="Sesi kıstım, pil de yüzde 80 abi."),
        ])
        b = BrainService(llm, self.cmd_bus)
        r = b.handle("abi sesi biraz kıs bi de pil ne durumda")
        self.rb.flush()

        assert r.executed == ("ses_ayarla", "pil_durumu")
        assert self.log == [SetVolume(delta=-10), GetBatteryStatus()]
        # Handler'ların kendi konuşması yakalandı → sese gitmedi
        assert self.rb.tts == []
        # Gözlemler modele geri verildi
        tool_msgs = [m for m in llm.calls[1]["messages"] if m["role"] == "tool"]
        assert "Ses ayarlandı -10" in tool_msgs[0]["content"]
        assert "Pil yüzdesi 80" in tool_msgs[1]["content"]
        assert tool_msgs[0]["tool_call_id"] == "id_ses_ayarla"

    def test_handler_hatasi_modele_hata_olarak_doner(self):
        llm = ScriptedLLM([
            LLMReply(tool_calls=(call("medya_kontrol", islem="sonraki"),)),
            LLMReply(text="Şarkıyı geçemedim, medya kontrolü çalışmıyor."),
        ])
        r = BrainService(llm, self.cmd_bus).handle("şarkıyı geç")
        tool_msg = [m for m in llm.calls[1]["messages"] if m["role"] == "tool"][0]
        assert tool_msg["content"].startswith("HATA") and "pyautogui" in tool_msg["content"]
        assert r.executed == ()

    def test_gecersiz_arac_argumani(self):
        llm = ScriptedLLM([LLMReply(tool_calls=(call("ses_ayarla"),)), LLMReply(text="Kaç olsun?")])
        r = BrainService(llm, self.cmd_bus).handle("sesi ayarla")
        assert r.reply == "Kaç olsun?" and self.log == []

    def test_tehlikeli_arac_acik_istek_olmadan_calismaz(self):
        llm = ScriptedLLM([LLMReply(tool_calls=(call("bilgisayari_kapat"),)), LLMReply(text="Emin misin?")])
        BrainService(llm, self.cmd_bus).handle("çok yoruldum ya")
        assert self.log == []

    def test_tehlikeli_arac_acik_istekle_calisir(self):
        llm = ScriptedLLM([LLMReply(tool_calls=(call("bilgisayari_kapat"),)), LLMReply(text="Kapatıyorum.")])
        BrainService(llm, self.cmd_bus).handle("bilgisayarı kapat artık")
        assert self.log == [ShutdownComputer(delay_seconds=60)]

    def test_sonsuz_arac_dongusu_kesilir(self):
        loop = [LLMReply(tool_calls=(call("pil_durumu"),))] * 10
        llm = ScriptedLLM(loop + [LLMReply(text="son")])
        b = BrainService(llm, self.cmd_bus, max_tool_rounds=2)
        b.handle("pil")
        assert len(llm.calls) == 3
        assert llm.calls[-1]["tools"] is None   # son turda araç verilmedi

    def test_bos_cevaba_varsayilan(self):
        llm = ScriptedLLM([LLMReply(tool_calls=(call("pil_durumu"),)), LLMReply(text="")])
        assert BrainService(llm, self.cmd_bus).handle("pil").reply == "Tamamdır."

    def test_gecmis_tutulur_ve_uslup_talimata_girer(self):
        llm = ScriptedLLM([LLMReply(text="a"), LLMReply(text="b")])
        b = BrainService(llm, self.cmd_bus, kullanici_adi="Ata")
        b.handle("kanka naber ya")
        b.observe_fast_path("ses kıs", "SetVolume")
        b.handle("abi ne yapıyoruz bugün")
        msgs = llm.calls[1]["messages"]
        assert msgs[0]["role"] == "system" and "Kanka gibi" in msgs[0]["content"]
        contents = [m["content"] for m in msgs[1:]]
        assert contents == ["kanka naber ya", "a", "ses kıs", "(yapıldı: SetVolume)", "abi ne yapıyoruz bugün"]

    def test_gecmis_sinirli(self):
        llm = ScriptedLLM([LLMReply(text=str(i)) for i in range(10)])
        b = BrainService(llm, self.cmd_bus, max_history_turns=2)
        for i in range(6):
            b.handle(f"mesaj {i}")
        assert len(llm.calls[-1]["messages"]) == 1 + 4 + 1

    def test_beyne_ulasilamazsa_llmerror(self):
        b = BrainService(HybridLLMClient([FailingLLM("x")]), self.cmd_bus)
        with pytest.raises(LLMError):
            b.handle("selam")


# ---------------------------------------------------------------------------
# IntentModulu — yönlendirme
# ---------------------------------------------------------------------------

class TestIntentRouting:

    def setup_method(self):
        from modules.intent_modulu import IntentModulu
        self.rb = RecordingBus()
        self.cmd_bus, self.log = make_cmd_bus(self.rb)
        self.IntentModulu = IntentModulu

    def teardown_method(self):
        self.rb.flush()

    def _run(self, text, brain):
        m = self.IntentModulu(self.rb, self.cmd_bus, brain=brain)
        m._ses_islendi(SpeechRecognized(text=text))
        self.rb.flush()

    def test_hizli_yol_kisa_komut_beyne_gitmez(self):
        llm = ScriptedLLM([])
        brain = BrainService(llm, self.cmd_bus)
        self._run("sesi kıs", brain)
        assert llm.calls == []
        assert any(isinstance(c, SetVolume) for c in self.log)
        # beyin geçmişine yazıldı
        assert brain.analyzer.gozlem_sayisi == 1

    def test_anlama_motorunun_bilmedigi_cumle_beyne_gider(self):
        llm = ScriptedLLM([LLMReply(tool_calls=(call("ses_ayarla", degisim=-10),)),
                           LLMReply(text="Kıstım abi, dinlen biraz.")])
        self._run("bugün kendimi çok yorgun hissediyorum ortamı sakinleştir", BrainService(llm, self.cmd_bus))
        assert len(llm.calls) == 2
        assert self.log == [SetVolume(delta=-10)]
        assert self.rb.tts == ["Kıstım abi, dinlen biraz."]

    def test_uzun_ama_net_komut_beyne_gitmeden_yapilir(self):
        llm = ScriptedLLM([])
        self._run("abi şu müziği biraz alçalt da kafam şişti", BrainService(llm, self.cmd_bus))
        assert llm.calls == []
        assert self.log == [SetVolume(delta=-10)]
        assert self.rb.tts == ["Ses ayarlandı -10"]   # handler'ın kendi sözü tek sefer söylenir

    def test_selamlasma_beyne_gider(self):
        llm = ScriptedLLM([LLMReply(text="Selam Ata!")])
        self._run("selam", BrainService(llm, self.cmd_bus))
        assert self.rb.tts == ["Selam Ata!"]

    def test_net_bilesik_komut_beyinsiz_yapilir(self):
        llm = ScriptedLLM([])
        from irle.domain.commands import CompositeCommand
        self.cmd_bus.register(CompositeCommand, lambda c: [self.cmd_bus.dispatch(x) for x in c.commands])
        self._run("chrome aç ve sesi kıs", BrainService(llm, self.cmd_bus))
        assert llm.calls == []
        assert OpenApplication(name="chrome") in self.log and SetVolume(delta=-15) in self.log

    def test_beyin_yoksa_anlamadim(self):
        self._run("asdfgh qwerty", None)
        assert self.rb.tts and self.rb.tts[0] in ANLAMADIM

    def test_beyin_ulasilamazsa_kurala_doner(self):
        brain = BrainService(HybridLLMClient([FailingLLM("x")]), self.cmd_bus)
        self._run("abi şu sesi bi kıs ya lütfen kanka", brain)
        assert any(isinstance(c, SetVolume) for c in self.log)

    def test_beyin_ulasilamazsa_ve_kural_yoksa_ozur(self):
        brain = BrainService(HybridLLMClient([FailingLLM("x")]), self.cmd_bus)
        self._run("dünyanın en yüksek dağı hangisi sence", brain)
        assert self.rb.tts and self.rb.tts[0] in ANLAMADIM


# ---------------------------------------------------------------------------
# Ayarlar ve .env
# ---------------------------------------------------------------------------

class TestBrainSettings:

    def test_varsayilanlar(self, monkeypatch):
        for k in ("IRLE_BEYIN_MODU", "GROQ_API_KEY", "IRLE_GROQ_API_KEY", "IRLE_OLLAMA_MODEL"):
            monkeypatch.delenv(k, raising=False)
        s = Settings()
        assert s.brain_mode == "hibrit" and s.groq_api_key == ""
        assert s.ollama_model == "qwen2.5:7b"

    def test_anahtar_repr_de_gizli(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "gsk_gizli123")
        s = Settings()
        assert s.groq_api_key == "gsk_gizli123"
        assert "gsk_gizli123" not in repr(s)

    def test_dotenv(self, tmp_path, monkeypatch):
        monkeypatch.delenv("IRLE_TEST_A", raising=False)
        monkeypatch.delenv("IRLE_TEST_B", raising=False)
        monkeypatch.setenv("IRLE_TEST_C", "dokunma")
        f = tmp_path / ".env"
        f.write_text('# yorum\nIRLE_TEST_A=1\nexport IRLE_TEST_B="iki kelime"\n'
                     'IRLE_TEST_C=ezme\nbozuk satır\n', encoding="utf-8")
        assert load_dotenv(str(f)) == 2
        assert os.environ["IRLE_TEST_A"] == "1"
        assert os.environ["IRLE_TEST_B"] == "iki kelime"
        assert os.environ["IRLE_TEST_C"] == "dokunma"
        monkeypatch.delenv("IRLE_TEST_A")
        monkeypatch.delenv("IRLE_TEST_B")

    @pytest.mark.parametrize("mode,key,expected", [
        ("hibrit", "k", ["groq:", "ollama:"]),
        ("hibrit", "", ["ollama:"]),
        ("bulut", "k", ["groq:"]),
        ("yerel", "k", ["ollama:"]),
    ])
    def test_fabrika(self, monkeypatch, mode, key, expected):
        from irle.app.brain_factory import build_brain
        monkeypatch.setenv("IRLE_BEYIN_MODU", mode)
        monkeypatch.setenv("GROQ_API_KEY", key)
        b = build_brain(Settings(), CommandBus(TypedEventBus()))
        names = b._llm.providers
        assert [n.split(":")[0] + ":" for n in names] == expected

    def test_fabrika_kapali(self, monkeypatch):
        from irle.app.brain_factory import build_brain
        monkeypatch.setenv("IRLE_BEYIN_MODU", "kapali")
        assert build_brain(Settings(), CommandBus(TypedEventBus())) is None
