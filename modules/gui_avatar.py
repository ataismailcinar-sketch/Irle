# -*- coding: utf-8 -*-
"""
=============================================================================
GUI AVATAR — Kıpçak Maskeli Kafa (İrle'nin yüzü)
=============================================================================
13. yüzyıl Kıpçak savaşçılarının yüz maskeli sivri miğferlerinden esinlenen,
tamamen kodla çizilmiş (resim dosyası yok) animasyonlu bir kafa:

    • Sivri, dilimli miğfer + altın kenar bandı ve perçinler
    • Kemerli kaşlardan inen burun siperi, badem göz yarıkları
    • Kıvrık bıyık, ince ağız yarığı
    • Yanlardan ve alttan sarkan zincir zırh (avantay)
    • Etrafında dönen Göktürk (Orhun) harfleri halkası

Durumlar (renk + davranış):
    dinliyor   — mavi, sakin nefes, ara sıra göz kırpar
    duyuyor    — turkuaz, gözler parlar (mikrofon konuşma yakaladı)
    dusunuyor  — mor, halka hızla döner, harfler sırayla yanar
    konusuyor  — altın, ağız konuşur (Piper'da çalan sesin gerçek şiddetiyle), hale dalgalanır
    hata       — kırmızı, kısa titreşim, sonra eski duruma döner
    bekliyor   — soluk altın (sessiz mod)

Kullanım:
    avatar = KipcakMaske(pencere, boyut=260, arkaplan="#0f1117")
    avatar.pack()
    avatar.durum("konusuyor")
=============================================================================
"""

from __future__ import annotations

import math
import random

try:
    from irle.infra.ses_seviyesi import seviye_olcer
except ImportError:  # src yolu ekli değilse dudak senkronu olmadan çalış
    seviye_olcer = None

try:
    import tkinter as tk
    import tkinter.font as tkfont
    _TemelTuval = tk.Canvas
except ImportError:  # Tkinter'sız ortamlarda yardımcı fonksiyonlar yine kullanılabilsin
    tk = None  # type: ignore[assignment]
    tkfont = None  # type: ignore[assignment]
    _TemelTuval = object  # type: ignore[assignment,misc]

DURUM_RENK = {
    "dinliyor": "#38bdf8",
    "duyuyor": "#22d3ee",
    "dusunuyor": "#a78bfa",
    "konusuyor": "#fbbf24",
    "hata": "#f87171",
    "bekliyor": "#a1873a",
}
_NABIZ_HIZI = {"dinliyor": 1.4, "duyuyor": 6.0, "dusunuyor": 3.5, "konusuyor": 2.5, "hata": 14.0, "bekliyor": 0.8}
_HALKA_HIZI = {"dinliyor": 0.12, "duyuyor": 0.35, "dusunuyor": 1.6, "konusuyor": 0.25, "hata": 0.0, "bekliyor": 0.04}
_ZAMAN_ASIMI = {"duyuyor": 12.0, "dusunuyor": 25.0, "hata": 1.5}   # takılı kalırsa dinliyor'a dön

# "Tengri : Türk : Bilge : İrle :" — Orhun yazısıyla (Old Turkic Unicode bloğu)
_RUNLER = "𐱅𐰭𐰼𐰃⁚𐱅𐰇𐰼𐰚⁚𐰋𐰃𐰠𐰏𐰀⁚𐰃𐰼𐰠𐰀⁚"

# Metal paleti
CELIK = "#3a4252"
CELIK_ACIK = "#4b566b"
CELIK_KOYU = "#232936"
ZINCIR = "#3d4658"
ZINCIR_PARLAK = "#4f5a6e"
ALTIN = "#c9a227"
ALTIN_KOYU = "#7a5c12"
YARIK = "#06080c"


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def karistir(c1: str, c2: str, t: float) -> str:
    """İki rengi t oranında karıştırır (0 → c1, 1 → c2)."""
    t = max(0.0, min(1.0, t))
    a, b = _hex(c1), _hex(c2)
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _ayna(noktalar: list[float]) -> list[float]:
    """Sol yüz parçasını sağa aynalar (x → 320 - x)."""
    out = []
    for i in range(0, len(noktalar), 2):
        out += [320 - noktalar[i], noktalar[i + 1]]
    return out


def _icinde(x: float, y: float, poligon: list[float]) -> bool:
    """Nokta poligonun içinde mi? (ışın atma)"""
    n = len(poligon) // 2
    ic = False
    j = n - 1
    for i in range(n):
        xi, yi = poligon[2 * i], poligon[2 * i + 1]
        xj, yj = poligon[2 * j], poligon[2 * j + 1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-9) + xi:
            ic = not ic
        j = i
    return ic


# Sanal koordinat sistemi: 320 x 320, merkez x=160
_MIGFER = [160, 18, 170, 32, 186, 50, 204, 72, 218, 96, 226, 116, 227, 132,
           93, 132, 94, 116, 102, 96, 116, 72, 134, 50, 150, 32]
_MASKE = [108, 132, 212, 132, 215, 160, 209, 196, 197, 226, 179, 250, 160, 262,
          141, 250, 123, 226, 111, 196, 105, 160]
_AVANTAY = [96, 130, 224, 130, 236, 170, 244, 222, 232, 260, 200, 286, 160, 296,
            120, 286, 88, 260, 76, 222, 84, 170]
_KAS_SOL = [114, 152, 122, 142, 136, 137, 150, 140, 158, 148]
_GOZ_SOL = [121, 162, 131, 153, 145, 154, 154, 163, 143, 170, 128, 169]
_BIYIK_SOL = [158, 207, 147, 204, 133, 207, 121, 216, 113, 229, 115, 238, 121, 232,
              127, 224, 139, 217, 151, 214, 158, 215]
_BURUN = [153, 146, 167, 146, 172, 194, 166, 202, 154, 202, 148, 194]


class KipcakMaske(_TemelTuval):  # type: ignore[misc,valid-type]
    """Durumlara göre canlanan Kıpçak maskeli kafa."""

    def __init__(self, master: "tk.Misc", boyut: int = 260, arkaplan: str = "#0f1117",
                 fps: int = 25, **kw) -> None:
        super().__init__(master, width=boyut, height=boyut, bg=arkaplan, highlightthickness=0, **kw)
        self._s = boyut / 320.0
        self._bg = arkaplan
        self._ms = max(15, int(1000 / fps))
        self._durum = "dinliyor"
        self._onceki = "dinliyor"
        self._durum_zamani = 0.0
        self._renk = DURUM_RENK["dinliyor"]
        self._t = 0.0
        self._aci = 0.0
        self._kirpma_baslangic = -1.0
        self._sonraki_kirpma = random.uniform(2.5, 5.0)
        self._calisiyor = True
        self._agiz_acik = 0.0
        self._olcer = seviye_olcer
        self._ciz()
        self.after(self._ms, self._kare)

    # ------------------------------------------------------------------
    # Dış arayüz
    # ------------------------------------------------------------------

    @property
    def mevcut_durum(self) -> str:
        return self._durum

    def durum(self, ad: str) -> None:
        if ad not in DURUM_RENK:
            return
        if ad == "hata" and self._durum != "hata":
            self._onceki = self._durum
        self._durum = ad
        self._durum_zamani = self._t

    def durdur(self) -> None:
        self._calisiyor = False

    # ------------------------------------------------------------------
    # Çizim (bir kez)
    # ------------------------------------------------------------------

    def _p(self, noktalar: list[float]) -> list[float]:
        return [v * self._s for v in noktalar]

    def _oval(self, cx: float, cy: float, rx: float, ry: float) -> list[float]:
        s = self._s
        return [(cx - rx) * s, (cy - ry) * s, (cx + rx) * s, (cy + ry) * s]

    def _ciz(self) -> None:
        s = self._s
        # --- Hale (en arkada) -------------------------------------------
        self._hale = [self.create_oval(*self._oval(160, 168, r, r * 0.98), outline="", fill=self._bg)
                      for r in (150, 138, 126, 114)]

        # --- Göktürk harf halkası ---------------------------------------
        self._halka_ic = self.create_oval(*self._oval(160, 160, 141, 141), outline=CELIK_KOYU, width=max(1, s))
        self._halka_dis = self.create_oval(*self._oval(160, 160, 157, 157), outline=CELIK_KOYU, width=max(1, s))
        aileler = set(tkfont.families(self))
        self._run_fontu = next((f for f in ("Segoe UI Historic", "Noto Sans Old Turkic") if f in aileler), None)
        self._runler = []
        harfler = list(_RUNLER) * 2 if self._run_fontu else [None] * 28
        for i, h in enumerate(harfler):
            if self._run_fontu:
                self._runler.append(self.create_text(0, 0, text=h, fill=CELIK_KOYU,
                                                     font=(self._run_fontu, max(7, int(11 * s)))))
            else:
                self._runler.append(self.create_line(0, 0, 0, 0, fill=CELIK_KOYU, width=max(1, 1.5 * s)))
        self._run_sayisi = len(self._runler)

        # --- Zincir zırh (avantay) --------------------------------------
        self.create_polygon(*self._p(_AVANTAY), smooth=True, fill=CELIK_KOYU, outline="#11151d", width=2 * s)
        for sira, y in enumerate(range(138, 296, 6)):
            kayma = 3 if sira % 2 else 0
            for x in range(76, 246, 6):
                xx = x + kayma
                if _icinde(xx, y, _AVANTAY) and not _icinde(xx, y, _MASKE):
                    # ışık soldan üstten: sol üst halkalar biraz daha parlak
                    renk = ZINCIR_PARLAK if (xx < 140 and y < 220) else ZINCIR
                    self.create_oval(*self._oval(xx, y, 2.3, 1.8), outline=renk, width=max(1, 0.8 * s))

        # --- Miğfer ------------------------------------------------------
        self.create_polygon(*self._p(_MIGFER), smooth=True, fill=CELIK, outline=ALTIN_KOYU, width=2 * s)
        self.create_polygon(*self._p([158, 24, 150, 40, 140, 62, 132, 92, 130, 126, 146, 126, 150, 92,
                                      154, 60, 157, 38]),
                            smooth=True, fill=CELIK_ACIK, outline="")
        for dx in (-48, -24, 0, 24, 48):     # dilim kaburgaları
            self.create_line(*self._p([160, 22, 160 + dx * 0.62, 76, 160 + dx, 128]), smooth=True,
                             fill=ALTIN_KOYU, width=max(1, 1.6 * s))
        self.create_line(*self._p([160, 22, 160, 6]), fill=ALTIN, width=max(1, 2.2 * s))      # tepe sivrisi
        self.create_oval(*self._oval(160, 20, 5, 4), fill=ALTIN, outline=ALTIN_KOYU)
        self._tepe_tasi = self.create_oval(*self._oval(160, 6, 3, 3), fill=ALTIN, outline="")
        bant = [92, 124, 128, 120, 160, 119, 192, 120, 228, 124, 229, 136, 192, 132, 160, 131, 128, 132, 91, 136]
        self.create_polygon(*self._p(bant), smooth=True, fill=ALTIN_KOYU, outline=ALTIN, width=max(1, s))
        for x in range(100, 225, 16):        # perçinler
            self.create_oval(*self._oval(x, 128 + (abs(x - 160) / 60) ** 2 * 2, 2.4, 2.4), fill=ALTIN, outline="")

        # --- Maske ---------------------------------------------------------
        self.create_polygon(*self._p(_MASKE), smooth=True, fill=CELIK, outline=ALTIN_KOYU, width=2.2 * s)
        self.create_polygon(*self._p([114, 136, 150, 136, 146, 190, 134, 232, 124, 222, 113, 194, 110, 160]),
                            smooth=True, fill=CELIK_ACIK, outline="")
        # yanak oymaları
        for kenar in (lambda n: n, _ayna):
            self.create_line(*self._p(kenar([118, 186, 126, 198, 136, 204])), smooth=True,
                             fill=ALTIN_KOYU, width=max(1, 1.3 * s))
            self.create_line(*self._p(kenar([122, 200, 128, 212, 138, 216])), smooth=True,
                             fill=ALTIN_KOYU, width=max(1, 1.1 * s))

        # --- Göz parıltısı (yarıkların arkasında) ---------------------------
        self._goz_hale = [self.create_oval(*self._oval(cx, 162, 16, 9), fill=YARIK, outline="")
                          for cx in (138, 182)]
        # --- Göz yarıkları ----------------------------------------------------
        self._goz_yarik = [self.create_polygon(*self._p(_GOZ_SOL), smooth=True, fill=YARIK, outline=ALTIN_KOYU,
                                               width=max(1, s)),
                           self.create_polygon(*self._p(_ayna(_GOZ_SOL)), smooth=True, fill=YARIK,
                                               outline=ALTIN_KOYU, width=max(1, s))]
        self._gozbebek = [self.create_oval(*self._oval(cx, 162, 7, 4), fill=self._renk, outline="")
                          for cx in (138, 182)]

        # --- Burun siperi ve kaşlar -----------------------------------------
        self.create_polygon(*self._p(_BURUN), fill=CELIK_ACIK, outline=ALTIN_KOYU, width=max(1, 1.2 * s))
        self.create_line(*self._p([160, 120, 160, 148]), fill=ALTIN, width=max(2, 6 * s))      # siper
        self.create_line(*self._p(_KAS_SOL), smooth=True, fill=ALTIN, width=max(2, 5 * s), capstyle="round")
        self.create_line(*self._p(_ayna(_KAS_SOL)), smooth=True, fill=ALTIN, width=max(2, 5 * s), capstyle="round")

        # --- Ağız ve bıyık ---------------------------------------------------
        self._agiz_isik = self.create_oval(*self._oval(160, 226, 13, 1), fill=YARIK, outline="")
        self._agiz = self.create_oval(*self._oval(160, 226, 12, 2), fill=YARIK, outline=ALTIN_KOYU,
                                      width=max(1, s))
        for parca in (_BIYIK_SOL, _ayna(_BIYIK_SOL)):
            self.create_polygon(*self._p(parca), smooth=True, fill="#b8901f", outline=ALTIN_KOYU, width=max(1, s))
        # sakal ucu oyması
        self.create_line(*self._p([152, 244, 160, 254, 168, 244]), smooth=True, fill=ALTIN_KOYU,
                         width=max(1, 1.4 * s))

    # ------------------------------------------------------------------
    # Animasyon
    # ------------------------------------------------------------------

    def _kare(self) -> None:
        if not self._calisiyor:
            return
        try:
            self._guncelle(self._ms / 1000.0)
        except tk.TclError:
            return  # pencere kapandı
        self.after(self._ms, self._kare)

    def _guncelle(self, dt: float) -> None:
        self._t += dt
        t = self._t
        d = self._durum

        # Takılı kalan geçici durumlar
        limit = _ZAMAN_ASIMI.get(d)
        if limit is not None and t - self._durum_zamani > limit:
            self._durum = self._onceki if d == "hata" else "dinliyor"
            d = self._durum
            self._durum_zamani = t

        hedef = DURUM_RENK[d]
        self._renk = karistir(self._renk, hedef, 0.18)
        renk = self._renk
        nabiz = 0.5 + 0.5 * math.sin(t * _NABIZ_HIZI[d])

        # --- Hale ----------------------------------------------------------
        guc = {"bekliyor": 0.06, "dinliyor": 0.10, "duyuyor": 0.22, "dusunuyor": 0.16,
               "konusuyor": 0.18, "hata": 0.25}[d]
        # --- Ağız açıklığı: çalan sesin gerçek şiddeti (Piper) ya da ritim (Windows sesi)
        hedef_acik = 0.0
        if d == "konusuyor":
            gercek = self._olcer.seviye() if self._olcer is not None else None
            if gercek is not None:
                hedef_acik = gercek
            else:
                hedef_acik = 0.25 + 0.75 * abs(math.sin(t * 9.1) * math.sin(t * 3.7 + 1.1))
        hiz = 0.65 if hedef_acik > self._agiz_acik else 0.35     # hızlı açıl, yumuşak kapan
        self._agiz_acik += (hedef_acik - self._agiz_acik) * hiz
        dalga = self._agiz_acik if d == "konusuyor" else 0.0
        for i, oval in enumerate(self._hale):
            oran = guc * (0.35 + 0.65 * nabiz) * (i + 1) / len(self._hale) + dalga * 0.05 * (i + 1)
            self.itemconfigure(oval, fill=karistir(self._bg, renk, oran))

        # --- Göktürk halkası ---------------------------------------------------
        self._aci += _HALKA_HIZI[d] * dt
        s = self._s
        r = 149
        tepe = (self._aci * 2.5) % (2 * math.pi)
        for i, oge in enumerate(self._runler):
            a = self._aci + 2 * math.pi * i / self._run_sayisi
            x, y = (160 + r * math.cos(a)) * s, (160 + r * math.sin(a)) * s
            if d == "dusunuyor":
                fark = abs((a - tepe + math.pi) % (2 * math.pi) - math.pi)
                parlak = 0.25 + 0.75 * max(0.0, 1 - fark / 1.2)
            else:
                parlak = 0.22 + 0.25 * nabiz
            renk_run = karistir(CELIK_KOYU, renk, parlak)
            if self._run_fontu:
                self.coords(oge, x, y)
                self.itemconfigure(oge, fill=renk_run, angle=-math.degrees(a) - 90)
            else:
                # Font yoksa: kısa çentikler (rün çizgisi gibi)
                ux, uy = math.cos(a), math.sin(a)
                uzun = (5 if i % 3 else 8) * s
                self.coords(oge, x - ux * uzun, y - uy * uzun, x + ux * uzun, y + uy * uzun)
                self.itemconfigure(oge, fill=renk_run)
        self.itemconfigure(self._halka_ic, outline=karistir(CELIK_KOYU, renk, 0.25 + 0.2 * nabiz))
        self.itemconfigure(self._halka_dis, outline=karistir(CELIK_KOYU, renk, 0.15 + 0.15 * nabiz))
        self.itemconfigure(self._tepe_tasi, fill=karistir(ALTIN, renk, 0.4 + 0.5 * nabiz))

        # --- Gözler (kırpma dahil) ---------------------------------------------
        if d not in ("konusuyor", "hata") and t >= self._sonraki_kirpma and self._kirpma_baslangic < 0:
            self._kirpma_baslangic = t
        acik = 1.0
        if self._kirpma_baslangic >= 0:
            ilerleme = (t - self._kirpma_baslangic) / 0.18
            if ilerleme >= 1:
                self._kirpma_baslangic = -1.0
                self._sonraki_kirpma = t + random.uniform(2.5, 6.0)
            else:
                acik = abs(1 - 2 * ilerleme)
        titresim = math.sin(t * 60) * 1.5 if d == "hata" else 0.0
        parlaklik = {"duyuyor": 0.9, "hata": 0.9}.get(d, 0.45 + 0.35 * nabiz)
        for i, cx in enumerate((138, 182)):
            cx += titresim
            ry = max(0.4, 4.2 * acik * (1.25 if d == "duyuyor" else 1.0))
            self.coords(self._gozbebek[i], *self._oval(cx, 162, 7.5, ry))
            self.itemconfigure(self._gozbebek[i], fill=karistir(renk, "#ffffff", 0.15 + 0.35 * nabiz * parlaklik))
            self.coords(self._goz_hale[i], *self._oval(cx, 162, 17, 9 * max(0.3, acik)))
            self.itemconfigure(self._goz_hale[i], fill=karistir(YARIK, renk, 0.25 + 0.45 * parlaklik))

        # --- Ağız --------------------------------------------------------------
        acilma = self._agiz_acik
        self.coords(self._agiz, *self._oval(160, 226, 12 - 2 * acilma, 1.8 + 5.5 * acilma))
        self.coords(self._agiz_isik, *self._oval(160, 226, 15, 2 + 7 * acilma))
        self.itemconfigure(self._agiz, fill=karistir(YARIK, renk, 0.6 * acilma))
        self.itemconfigure(self._agiz_isik, fill=karistir(CELIK, renk, 0.35 * acilma))
