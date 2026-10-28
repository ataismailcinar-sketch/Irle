# -*- coding: utf-8 -*-
"""
=============================================================================
INFRA / KESME DİNLEYİCİ — İrle konuşurken araya giren sesi yakalama
=============================================================================
Yankı kilidi açıkken (İrle konuşuyor) mikrofon blokları buraya beslenir.
Amaç: hoparlörden gelen yankıyı değil, kullanıcının sesini yakalamak.

Sezgi: Kullanıcı konuşuyorsa, İrle'nin kelime/cümle aralarındaki SESSİZ
anlarda da mikrofonda güçlü ses olur. Yankı ise İrle sustuğunda söner.
Piper'ın çalan sesinin şiddeti (ses_seviyesi) bilindiği için bu ayrım yapılabilir.
Windows sesinde şiddet bilinmez; o zaman çok daha yüksek bir eşik kullanılır.

Bir parça "tanınmaya değer" bulunursa ham ses döndürülür; karar (dur / komut /
yankı) metne çevrildikten sonra `kesme.kesme_karari` ile verilir.
=============================================================================
"""

from __future__ import annotations

import time
from typing import Any, Callable, Optional


class KesmeDinleyici:

    def __init__(self, temel_esik: float = 220.0, carpan: float = 1.6, bilinmeyen_carpan: float = 2.5,
                 sessiz_seviye: float = 0.15, min_blok: int = 2, max_blok: int = 12,
                 bitis_sessizlik: int = 2, min_aralik_saniye: float = 2.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._esik = temel_esik * carpan
        self._esik_bilinmeyen = temel_esik * bilinmeyen_carpan
        self._sessiz_seviye = sessiz_seviye
        self._min = min_blok
        self._max = max_blok
        self._bitis = bitis_sessizlik
        self._aralik = min_aralik_saniye
        self._clock = clock
        self._son_gonderim = -1e9
        self.sifirla()

    def sifirla(self) -> None:
        self._toplanan: list[Any] = []
        self._sesli = 0
        self._temiz = 0
        self._sessiz = 0

    def besle(self, blok: Any, enerji: float, tts_seviyesi: Optional[float]) -> Optional[Any]:
        """Bir mikrofon bloğu ver; tanınmaya değer parça tamamlanırsa blok listesini döndürür."""
        yuksek = enerji >= self._esik
        if yuksek:
            self._toplanan.append(blok)
            self._sesli += 1
            self._sessiz = 0
            if tts_seviyesi is None:
                if enerji >= self._esik_bilinmeyen:
                    self._temiz += 1
            elif tts_seviyesi < self._sessiz_seviye:
                self._temiz += 1          # İrle o an susuyordu ama mikrofonda ses var → kullanıcı
        elif self._toplanan:
            self._toplanan.append(blok)
            self._sessiz += 1

        bitti = self._toplanan and (self._sessiz >= self._bitis or len(self._toplanan) >= self._max)
        if not bitti:
            return None

        parca, sesli, temiz = self._toplanan, self._sesli, self._temiz
        self.sifirla()
        if sesli < self._min or temiz < 1:
            return None
        simdi = self._clock()
        if simdi - self._son_gonderim < self._aralik:
            return None
        self._son_gonderim = simdi
        return parca
