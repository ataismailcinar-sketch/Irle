# -*- coding: utf-8 -*-
"""
=============================================================================
ADAPTERS / INTENT / UYANDIRMA — "İrle, ..." ile uyanma (metin tabanlı)
=============================================================================
Mikrofon sürekli açık; televizyon, müzik ya da yandaki sohbet komut
sanılabiliyor. Uyandırma kelimesi açıkken sadece "İrle ..." ile başlayan
cümleler işlenir. Cevaptan sonra kısa bir süre (sohbet penceresi) kelimeyi
tekrar söylemeden devam edilebilir.

Konuşmayı metne çevirme hataları için bulanık eşleşme yapılır
(irle / ırle / erle / irla / hirle ...).
=============================================================================
"""

from __future__ import annotations

import difflib
import re
import time
from typing import Callable, Optional

from irle.adapters.intent.nlu import tr_kucuk

# "irle"ye benzeyen ama gündelik olan kelimeler — bunlarla uyanma
_YANLIS_ALARM = {"ile", "işle", "eğer", "iri", "ilk", "irili", "erken", "ileri", "ilke", "ince"}


class UyandirmaFiltresi:

    def __init__(self, kelime: str = "irle", pencere_saniye: float = 20.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._kelime = tr_kucuk(kelime.strip())
        self._pencere = pencere_saniye
        self._clock = clock
        self._son = -1e9

    def _eslesir_mi(self, kelime: str) -> bool:
        k = re.sub(r"['’].*$", "", kelime)
        k = re.sub(r"[^\wçğıöşü]", "", k)
        if not k or k in _YANLIS_ALARM:
            return False
        if k == self._kelime or k.startswith(self._kelime):
            return True
        if abs(len(k) - len(self._kelime)) > 2:
            return False
        return difflib.SequenceMatcher(None, k, self._kelime).ratio() >= 0.75

    def filtrele(self, metin: str) -> Optional[str]:
        """İşlenecek metni döndürür.

        None → yok say (uyandırılmadı). "" → sadece "İrle" dendi (dinliyorum).
        """
        kelimeler = metin.strip().split()
        simdi = self._clock()
        for i, w in enumerate(kelimeler[:3]):
            if self._eslesir_mi(tr_kucuk(w)):
                self._son = simdi
                kalan = " ".join(kelimeler[i + 1:]).strip(" ,.!?")
                return kalan
        if simdi - self._son <= self._pencere:
            self._son = simdi
            return metin
        return None

    def etkilesim(self) -> None:
        """Asistan cevap verdi → sohbet penceresini yenile."""
        self._son = self._clock()
