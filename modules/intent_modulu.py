# -*- coding: utf-8 -*-
"""
=============================================================================
INTENT MODÜLÜ — Çevrimdışı Anlama + Hibrit Beyin
=============================================================================
Her cümle için sırayla:

  0. UYANDIRMA (opsiyonel) — IRLE_UYANDIRMA ayarlıysa sadece "İrle ..." ile
     başlayan cümleler ya da cevaptan sonraki kısa sohbet penceresi işlenir.

  1. ANLAMA MOTORU (TurkceNLU) — dil modeli yok, anında, çevrimdışı.
     "abi şu müziği biraz alçalt", "sesi yüzde kırk beş yap", "kroma aç",
     "biraz daha", "geri al", "onu kapat", "5 dakika sonra çayı hatırlat"...
     Güven yüksekse komut hemen çalışır ve üsluba uygun kısa bir cevap verilir.

  2. BEYİN (Groq → Ollama) — anlama motorunun emin olmadığı, sohbet içeren
     ya da bilgi isteyen cümleler. Beyin yoksa bu adım atlanır.

  3. YEDEK — beyne ulaşılamazsa: anlama motorunun düşük güvenli tahmini,
     hazır sohbet cevapları, eski regex kural motoru, en son "anlamadım".

Her durumda cevap kullanıcının üslubuna göre seçilir (kanka / resmî / kısa...).
=============================================================================
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from irle.adapters.brain.llm_client import LLMError
from irle.adapters.brain.persona import UslupAnalizcisi
from irle.adapters.intent.nlu import Baglam, NluSonuc, TurkceNLU, komut_kategorisi
from irle.adapters.intent.rule_engine import RuleEngine
from irle.adapters.intent.uyandirma import UyandirmaFiltresi
from irle.adapters.intent.yanitlar import YanitUretici
from irle.app.task_planner import CompoundIntentDecomposer
from irle.domain.commands import CompositeCommand, OpenApplication, Speak
from irle.domain.events import (
    AssistantReplied,
    IntentResolved,
    IntentUnresolved,
    MemorySaveRequested,
    SpeechRecognized,
)
from irle.infra.speech_capture import capture_speech

logger = logging.getLogger("irle.modules.intent")

# Beyin varken anlama motoruna güvenmek için gereken eşik (altı → beyne sor)
ESIK_BEYINLI = 0.8
# Beyin yokken / ulaşılamazken anlama motorunun tahmini için eşik
ESIK_BEYINSIZ = 0.5
# Eski regex hızlı yolunun güvenle kullanılacağı en uzun cümle (kelime)
HIZLI_YOL_MAX_KELIME = 5


def hizli_yol_uygun_mu(metin: str, sonuc: Any) -> bool:
    """Eski regex sonucu beyne sormadan çalıştırılabilecek kadar güvenilir mi?"""
    if sonuc is None or isinstance(sonuc, (Speak, CompositeCommand)):
        return False
    if len(metin.split()) > HIZLI_YOL_MAX_KELIME:
        return False
    if CompoundIntentDecomposer.CONJUNCTION_PATTERN.search(metin):
        return False
    if isinstance(sonuc, OpenApplication) and len(sonuc.name.split()) > 2:
        return False
    return True


def _hata_metni(hata: str) -> str:
    hata = (hata or "").strip().rstrip(".!")
    return hata[0].lower() + hata[1:] if hata else "bir sorun çıktı"


class IntentModulu:
    """Türkçe anlama motoru + hibrit LLM beyin + üsluba uyan cevaplar."""

    def __init__(self, event_bus: Any, command_bus: Any, brain: Optional[Any] = None,
                 settings: Any = None, nlu: Optional[TurkceNLU] = None,
                 yanitlar: Optional[YanitUretici] = None) -> None:
        self._bus = event_bus
        self._cmd_bus = command_bus
        self._brain = brain
        self._engine = RuleEngine()
        self._decomposer = CompoundIntentDecomposer(self._engine)
        self._nlu = nlu or TurkceNLU()
        self._baglam = Baglam()
        self.analyzer: UslupAnalizcisi = brain.analyzer if brain is not None else UslupAnalizcisi()
        self._yanit = yanitlar or YanitUretici(
            asistan_adi=getattr(settings, "assistant_name", "İrle") or "İrle",
            kullanici_adi=getattr(settings, "user_name", "") or "",
        )
        wake = getattr(settings, "wake_word", "") if settings is not None else ""
        self._uyandirma = (UyandirmaFiltresi(wake, getattr(settings, "wake_window", 20.0))
                           if wake else None)

        self._bus.subscribe(SpeechRecognized, self._ses_islendi)

    def baslat(self) -> None:
        mod = "anlama motoru + hibrit beyin" if self._brain else "anlama motoru (çevrimdışı)"
        uyan = f", uyandırma: '{self._uyandirma._kelime}'" if self._uyandirma else ""
        logger.info("Intent Modülü başlatıldı (%s%s).", mod, uyan)

    def durdur(self) -> None:
        logger.info("Intent Modülü durduruldu.")

    # ------------------------------------------------------------------
    # Ana akış
    # ------------------------------------------------------------------

    def _ses_islendi(self, event: SpeechRecognized) -> None:
        metin = event.text.strip()
        if not metin:
            return

        if self._uyandirma is not None:
            filtreli = self._uyandirma.filtrele(metin)
            if filtreli is None:
                logger.debug("Uyandırma kelimesi yok, yok sayıldı: %r", metin)
                return
            if not filtreli:
                self._gozlemle(metin)
                self._cevap_ver(self._uret("dinliyorum"))
                return
            metin = filtreli

        logger.info("Intent modülü işliyor → %r", metin)
        self._bellege("kullanici", metin)

        nlu = self._nlu_guvenli(metin)
        esik = ESIK_BEYINLI if self._brain is not None else ESIK_BEYINSIZ

        # 1) Anlama motoru eminse: hemen yap
        if nlu is not None and nlu.guven >= esik:
            if nlu.komut is not None and nlu.tur in ("komut", "baglam"):
                self._gozlemle(metin)
                self._hizli(metin, nlu.komut, nlu.kategori, nlu.alanlar, kaynak=f"nlu:{nlu.niyet}")
                return
            if nlu.tur in ("olumsuz", "baglam"):      # "sesi kısma", tekrarlanacak şey yok
                self._gozlemle(metin)
                self._cevap_ver(self._uret(nlu.kategori))
                return
            if nlu.tur == "sohbet" and self._brain is None:
                self._gozlemle(metin)
                self._cevap_ver(self._uret(nlu.kategori))
                return

        kural = self._engine.parse(metin)

        # 1b) Eski regex hızlı yolu (anlama motorunun kaçırdığı kalıplar)
        if self._brain is not None and hizli_yol_uygun_mu(metin, kural):
            self._gozlemle(metin)
            self._hizli(metin, kural, komut_kategorisi(kural), {}, kaynak="regex")
            return

        # 2) Beyin
        gozlendi = False
        if self._brain is not None:
            try:
                sonuc = self._brain.handle(metin)   # beyin üslubu kendisi gözlemler
                self._yayinla(IntentResolved(
                    source_text=metin, command_type="Brain:" + (",".join(sonuc.executed) or "sohbet")))
                self._cevap_ver(sonuc.reply)
                return
            except LLMError as exc:
                gozlendi = True
                logger.warning("Beyne ulaşılamadı, çevrimdışı moda dönülüyor: %s", exc)
            except Exception as exc:
                gozlendi = True
                logger.error("Beyin hatası, çevrimdışı moda dönülüyor: %s", exc, exc_info=True)

        if not gozlendi:
            self._gozlemle(metin)

        # 3) Yedek
        if nlu is not None and nlu.guven >= ESIK_BEYINSIZ:
            if nlu.komut is not None and nlu.tur in ("komut", "baglam"):
                self._hizli(metin, nlu.komut, nlu.kategori, nlu.alanlar, kaynak=f"nlu-yedek:{nlu.niyet}",
                            beyne_bildir=not gozlendi)
            else:
                self._cevap_ver(self._uret(nlu.kategori))
            return

        yedek = self._decomposer.decompose_and_parse(metin) or kural
        if yedek is not None:
            self._hizli(metin, yedek, komut_kategorisi(yedek), {}, kaynak="regex-yedek",
                        beyne_bildir=not gozlendi)
            return

        self._yayinla(IntentUnresolved(source_text=metin))
        self._cevap_ver(self._uret("anlamadim"))

    # ------------------------------------------------------------------
    # Yardımcılar
    # ------------------------------------------------------------------

    def _nlu_guvenli(self, metin: str) -> Optional[NluSonuc]:
        try:
            return self._nlu.anla(metin, self._baglam)
        except Exception as exc:
            logger.error("Anlama motoru hatası: %s", exc, exc_info=True)
            return None

    def _hizli(self, metin: str, komut: Any, kategori: str, alanlar: dict, kaynak: str,
               beyne_bildir: bool = True) -> None:
        """Komutu çalıştırır; handler'ın sözünü ya da üsluba uygun onayı söyler."""
        logger.info("⚡ [%s | %s] %r → %s", kaynak, self.analyzer.profil().etiket(), metin, komut)
        self._yayinla(IntentResolved(source_text=metin, command_type=type(komut).__name__))

        with capture_speech() as yakalanan:
            self._cmd_bus.dispatch(komut)

        if yakalanan.errors:
            cevap = self._uret("hata", detay=_hata_metni(yakalanan.errors[0]))
        else:
            self._baglam.komut_calisti(komut, alanlar.get("ad", ""))
            if yakalanan.texts:
                cevap = " ".join(t.strip() for t in yakalanan.texts if t.strip())
            elif kategori == "onay" and yakalanan.notifications:
                # Genel onay yerine handler'ın bilgilendirici mesajı ("60 saniye sonra kapanacak")
                cevap = yakalanan.notifications[-1]
            else:
                cevap = self._uret(kategori, **alanlar)

        if self._brain is not None and beyne_bildir:
            # Beyin bağlamı kaçırmasın ("onu biraz daha kıs" gibi devam cümleleri için)
            self._brain.observe_fast_path(metin, f"{type(komut).__name__} → {cevap}")
        self._cevap_ver(cevap)

    def _gozlemle(self, metin: str) -> None:
        # Beyin varsa observe_fast_path / handle zaten gözlemler (aynı analizci)
        if self._brain is None:
            self.analyzer.gozlemle(metin)

    def _uret(self, kategori: str, **alanlar: Any) -> str:
        return self._yanit.uret(kategori, self.analyzer.profil(), **alanlar)

    def _cevap_ver(self, metin: str) -> None:
        if not metin:
            return
        self._baglam.yanit_verildi(metin)
        if self._uyandirma is not None:
            self._uyandirma.etkilesim()
        self._bellege("asistan", metin)
        self._yayinla(AssistantReplied(action="konuş", reply_text=metin))
        self._cmd_bus.dispatch(Speak(text=metin))

    def _bellege(self, role: str, text: str) -> None:
        self._yayinla(MemorySaveRequested(role=role, text=text))

    def _yayinla(self, event: Any) -> None:
        try:
            self._bus.publish(event)
        except Exception as exc:
            logger.error("%s yayınlanamadı: %s", type(event).__name__, exc)
