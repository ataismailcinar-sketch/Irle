# -*- coding: utf-8 -*-
"""
=============================================================================
ADAPTERS / INTENT / KESME — İrle konuşurken araya girme kararı
=============================================================================
İrle konuşurken mikrofonun duyduğu bir cümle için karar verir:

    "dur", "sus", "yeter", "tamam tamam", "İrle dur"      → ("dur", None)
    "İrle sesi kıs" (uyandırma kelimesi + komut)            → ("komut", "İrle sesi kıs")
    İrle'nin kendi söylediğine benzeyen metin (yankı)       → None
    diğer her şey                                           → None

Yanlış alarm, yanlış "durmamak"tan daha kötü: bu yüzden kurallar temkinli.
Durma kelimesi sadece kısa bir cümlede (≤ 4 kelime) geçerli.
=============================================================================
"""

from __future__ import annotations

import difflib
import re
from typing import Iterable, Optional

from irle.adapters.intent.nlu import tr_kucuk

_DUR = re.compile(
    r"^(?:(?:hey\s+)?[iıe]rl[ea]\w*\s+)?"
    r"(?:dur\w*|sus\w*|yeter\w*|kes\b|kes\s+art[ıi]k|tamam\s+tamam|tamam\s+yeter|"
    r"sessiz\s+ol\w*|bekle\w*|stop|kapa\s+[çc]ene\w*|ok\s+tamam|anlad[ıi]m\s+tamam)"
    r"(?:\s+(?:art[ıi]k|l[uü]tfen|bi|abi|kanka|ya|be|bakal[ıi]m|bir\s+saniye|bi\s+saniye))*$"
)
_UYANDIRMA = re.compile(r"^(?:hey\s+)?([iıe]rl[ea])\w*\b[\s,]*(.+)$")


def _sade(metin: str) -> str:
    s = tr_kucuk(metin)
    s = re.sub(r"['’][a-zçğıöşü]*", "", s)
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def yanki_mi(duyulan: str, soylenenler: Iterable[str], esik: float = 0.55) -> bool:
    """Duyulan metin İrle'nin söylediklerinden birinin parçası mı?"""
    d = _sade(duyulan)
    if not d:
        return True
    d_kelime = d.split()
    for s in soylenenler:
        s = _sade(s)
        if not s:
            continue
        if d in s:
            return True
        s_kelime = s.split()
        # duyulan kelimelerin çoğu söylenende geçiyor mu?
        ortak = sum(1 for w in d_kelime if any(
            w == x or (len(w) > 3 and difflib.SequenceMatcher(None, w, x).ratio() > 0.8) for x in s_kelime))
        if ortak / len(d_kelime) >= 0.7:
            return True
        if difflib.SequenceMatcher(None, d, s).ratio() >= esik:
            return True
    return False


def kesme_karari(duyulan: str, soylenenler: Iterable[str] = ()) -> Optional[tuple[str, Optional[str]]]:
    soylenenler = list(soylenenler)
    sade = _sade(duyulan)
    if not sade:
        return None
    kelimeler = sade.split()

    if len(kelimeler) <= 4 and _DUR.match(sade):
        # İrle cümlesinde "dur" geçiyorsa ve duyulan sadece o kelimeyse bu yankı olabilir
        if not (len(kelimeler) == 1 and yanki_mi(sade, soylenenler)):
            return ("dur", None)
        return None

    if yanki_mi(duyulan, soylenenler):
        return None

    m = _UYANDIRMA.match(sade)
    if m and len(m.group(2).split()) >= 1:
        return ("komut", duyulan.strip())
    return None
