# -*- coding: utf-8 -*-
"""
=============================================================================
ADAPTERS / VISION / EL JESTLERİ — Elle fare kontrolü (kameradan bağımsız mantık)
=============================================================================
Girdi: MediaPipe'ın 21 el noktası (x, y normalleştirilmiş görüntü koordinatı).
Çıktı: imleç konumu (0-1) + olaylar (tıkla, sağ tıkla, basılı tut, bırak, kaydır).

JESTLER (tek ve net):
    ✋ Açık el, hareket et      → imleç (AVUÇ ortası izlenir, parmaklar oynasa da kaymaz)
    👌 Başparmak + işaret       → kısa: TIKLA        uzun (0.4 sn+): SÜRÜKLE, açınca BIRAK
    🤌 Başparmak + orta parmak  → SAĞ TIKLA
    ✌️  İki parmak (işaret+orta) → yukarı/aşağı hareket: KAYDIR (imleç durur)
    ✊ Yumruk                   → imleç donar; elini başka yere götürüp açınca imleç
                                  KALDIĞI YERDEN devam eder (fareyi masadan kaldırmak gibi)
    👉 Eli kameraya doğru it    → TIKLA (derinlik: avucun büyüklüğü hızla artarsa)
    🤘 Bozkurt (1 sn tut)       → el kontrolünü aç / kapat

DERİNLİK nasıl ölçülür?
    MediaPipe'ın `z` değeri bileğe göre görelidir ve gürültülüdür; kameraya uzaklığı
    göstermez. Bunun yerine avucun görüntüdeki BÜYÜKLÜĞÜ kullanılır (bilek→parmak
    kökleri + avuç genişliği ortalaması): el yaklaştıkça büyür. Yavaşça yaklaşmak
    tıklamaz (taban çizgisi uyum sağlar); sadece ~0.35 sn içinde %15+ büyüme "itme"dir.
    Tıklama, itme başlamadan önceki imleç konumuna yapılır (el ilerlerken kayar).
=============================================================================
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Optional, Sequence

# MediaPipe el noktası indeksleri
BILEK = 0
BAS_UC = 4
ISARET = (5, 6, 7, 8)      # MCP, PIP, DIP, uç
ORTA = (9, 10, 11, 12)
YUZUK = (13, 14, 15, 16)
SERCE = (17, 18, 19, 20)


@dataclass
class ElAyarlari:
    pinch_kapan: float = 0.30        # başparmak-işaret mesafesi / avuç < bu → birleşti
    pinch_acil: float = 0.42         # > bu → ayrıldı (histerezis)
    surukleme_suresi: float = 0.40   # bu kadar tutulan pinch → sürükleme
    sag_tik_bekleme: float = 0.5
    kaydirma_kazanc: float = 40.0    # el hareketi (avuç boyu cinsinden) → tekerlek çentiği
    itme_aktif: bool = True
    itme_orani: float = 1.15         # avuç taban boyunun bu katına çıkarsa
    itme_artis: float = 0.12         # ve son itme_pencere içinde en az bu kadar arttıysa
    itme_pencere: float = 0.35
    itme_birak_orani: float = 1.07
    itme_bekleme: float = 0.6
    taban_uyum: float = 0.04         # avuç taban boyu ne hızla uyum sağlar (kare başı)
    referans_avuc: float = 0.13      # tipik avuç boyu (kol mesafesinde)
    kenar_payi: float = 0.12         # kontrol kutusu kenar payı (referans mesafede)
    bozkurt_suresi: float = 0.8


@dataclass
class ElCikti:
    imlec: Optional[tuple[float, float]] = None
    olaylar: list[tuple[str, Any]] = field(default_factory=list)
    jest: str = "yok"                 # ekranda gösterilecek
    derinlik: float = 1.0             # avuç / taban (1.0 = normal)
    pinch: float = 1.0
    avuc: float = 0.0


def _nokta(lm: Any) -> tuple[float, float]:
    if isinstance(lm, (tuple, list)):
        return float(lm[0]), float(lm[1])
    return float(lm.x), float(lm.y)


def _mesafe(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


class ElKontrolcu:
    """Her kamera karesinde `isle(noktalar, zaman)` çağrılır."""

    def __init__(self, ayarlar: Optional[ElAyarlari] = None) -> None:
        self.a = ayarlar or ElAyarlari()
        self.sifirla()

    def sifirla(self) -> None:
        self._pinch = False
        self._pinch_bas = 0.0
        self._pinch_kilit: Optional[tuple[float, float]] = None
        self._surukluyor = False
        self._sag_pinch = False
        self._son_sag = -1e9
        self._taban: Optional[float] = None
        self._itiliyor = False
        self._itme_bas = 0.0
        self._son_itme = -1e9
        self._gecmis: Deque[tuple[float, float, Optional[tuple[float, float]]]] = deque(maxlen=60)
        self._kaydirma_y: Optional[float] = None
        self._kaydirma_birikim = 0.0
        self._bozkurt_bas: Optional[float] = None
        self._bozkurt_tetiklendi = False
        self._ofset = (0.0, 0.0)                     # yumrukla "kavrama" sonrası kaydırma
        self._son_imlec: Optional[tuple[float, float]] = None
        self._kavrama_bekliyor = False

    # ------------------------------------------------------------------
    # Özellikler
    # ------------------------------------------------------------------

    @staticmethod
    def avuc_boyu(p: Sequence[tuple[float, float]]) -> float:
        """Kameraya uzaklığın ölçüsü: bilek→kökler + avuç genişliği ortalaması."""
        b = p[BILEK]
        return (_mesafe(b, p[5]) + _mesafe(b, p[9]) + _mesafe(b, p[17]) + _mesafe(p[5], p[17])) / 4.0

    @staticmethod
    def _acik_mi(p: Sequence[tuple[float, float]], parmak: tuple[int, int, int, int]) -> bool:
        b = p[BILEK]
        return _mesafe(b, p[parmak[3]]) > _mesafe(b, p[parmak[1]]) * 1.08

    def _imlec_haritala(self, p: Sequence[tuple[float, float]], avuc: float) -> tuple[float, float]:
        # Avuç ortası: parmak hareketlerinden etkilenmez
        xs = [p[i][0] for i in (0, 5, 9, 13, 17)]
        ys = [p[i][1] for i in (0, 5, 9, 13, 17)]
        x_ham = 1.0 - sum(xs) / 5.0            # ayna: elini sağa götür → imleç sağa
        y_ham = sum(ys) / 5.0
        # Uzaktayken el görüntüde küçük hareket eder → kontrol kutusu küçülür
        olcek = self.a.referans_avuc / max(avuc, 0.03)
        pay = min(0.32, max(0.04, self.a.kenar_payi * olcek))
        # Kutunun dikey merkezi biraz yukarıda: el doğal olarak göğüs hizasında durur
        x = (x_ham - pay) / (1.0 - 2 * pay)
        y = (y_ham - pay * 0.8) / (1.0 - 2 * pay)
        return min(1.0, max(0.0, x)), min(1.0, max(0.0, y))

    def _gecmisten(self, t: float, sn_once: float) -> Optional[tuple[float, float]]:
        for zt, _, poz in reversed(self._gecmis):
            if t - zt >= sn_once and poz is not None:
                return poz
        return self._gecmis[0][2] if self._gecmis else None

    # ------------------------------------------------------------------
    # Ana işlem
    # ------------------------------------------------------------------

    def isle(self, noktalar: Optional[Sequence[Any]], t: float) -> ElCikti:
        if not noktalar or len(noktalar) < 21:
            return self._el_yok()

        p = [_nokta(n) for n in noktalar]
        avuc = max(self.avuc_boyu(p), 1e-4)
        cikti = ElCikti(avuc=avuc)

        isaret_acik = self._acik_mi(p, ISARET)
        orta_acik = self._acik_mi(p, ORTA)
        yuzuk_acik = self._acik_mi(p, YUZUK)
        serce_acik = self._acik_mi(p, SERCE)
        pinch = _mesafe(p[BAS_UC], p[ISARET[3]]) / avuc
        sag = _mesafe(p[BAS_UC], p[ORTA[3]]) / avuc
        cikti.pinch = pinch

        # --- Bozkurt: işaret + serçe açık, orta + yüzük kapalı → (1 sn) aç/kapat ---
        if isaret_acik and serce_acik and not orta_acik and not yuzuk_acik:
            if self._bozkurt_bas is None:
                self._bozkurt_bas = t
            elif not self._bozkurt_tetiklendi and t - self._bozkurt_bas >= self.a.bozkurt_suresi:
                self._bozkurt_tetiklendi = True
                cikti.olaylar.append(("mod_degistir", None))
            cikti.jest = "bozkurt"
            return self._bitir(cikti, t, avuc, None)
        self._bozkurt_bas = None
        self._bozkurt_tetiklendi = False

        # --- Derinlik tabanı (sadece itme yokken uyum sağlar) ---
        if self._taban is None:
            self._taban = avuc
        derinlik = avuc / self._taban
        cikti.derinlik = derinlik

        # --- Yumruk: kavrama (imleç durur) ---
        if not (isaret_acik or orta_acik or yuzuk_acik or serce_acik) and pinch > self.a.pinch_acil \
                and not self._pinch:
            if self._surukluyor:
                cikti.olaylar.append(("birak", None))
            self._pinch = self._surukluyor = False
            self._kaydirma_y = None
            cikti.jest = "yumruk"
            self._kavrama_bekliyor = True
            self._taban_guncelle(avuc)
            return self._bitir(cikti, t, avuc, None)

        ham = self._imlec_haritala(p, avuc)
        if self._kavrama_bekliyor and self._son_imlec is not None:
            # El açıldı: imleç donduğu yerden devam etsin (fareyi kaldırıp koymak gibi)
            self._ofset = (self._son_imlec[0] - ham[0], self._son_imlec[1] - ham[1])
        self._kavrama_bekliyor = False
        imlec = (min(1.0, max(0.0, ham[0] + self._ofset[0])), min(1.0, max(0.0, ham[1] + self._ofset[1])))

        # --- İki parmak (V): kaydırma ---
        if isaret_acik and orta_acik and not yuzuk_acik and not serce_acik and pinch > self.a.pinch_acil \
                and not self._surukluyor:
            y = sum(p[i][1] for i in (0, 5, 9, 13, 17)) / 5.0
            if self._kaydirma_y is not None:
                self._kaydirma_birikim += (self._kaydirma_y - y) / avuc * self.a.kaydirma_kazanc / 10.0
                centik = int(self._kaydirma_birikim)
                if centik:
                    self._kaydirma_birikim -= centik
                    cikti.olaylar.append(("kaydir", centik))   # + yukarı, - aşağı
            self._kaydirma_y = y
            self._pinch = False
            cikti.jest = "kaydirma"
            self._taban_guncelle(avuc)
            return self._bitir(cikti, t, avuc, None)
        self._kaydirma_y = None
        self._kaydirma_birikim = 0.0

        # --- Sağ tık: başparmak + orta parmak (işaretten belirgin şekilde yakın) ---
        sag_birlesti = sag < self.a.pinch_kapan and sag < pinch * 0.7
        if sag_birlesti and not self._sag_pinch and t - self._son_sag >= self.a.sag_tik_bekleme \
                and not self._pinch:
            cikti.olaylar.append(("sag_tikla", None))
            self._son_sag = t
        self._sag_pinch = sag_birlesti
        if sag_birlesti:
            cikti.jest = "sag_tik"
            return self._bitir(cikti, t, avuc, self._gecmisten(t, 0.12) or imlec)

        # --- Sol pinch: tıkla / sürükle ---
        if not self._pinch and pinch < self.a.pinch_kapan:
            self._pinch = True
            self._pinch_bas = t
            self._pinch_kilit = self._gecmisten(t, 0.12) or imlec   # birleştirme öncesi konum
        elif self._pinch and pinch > self.a.pinch_acil:
            self._pinch = False
            if self._surukluyor:
                cikti.olaylar.append(("birak", None))
                self._surukluyor = False
            elif t - self._pinch_bas < self.a.surukleme_suresi:
                cikti.olaylar.append(("tikla", self._pinch_kilit))
            # kısa sürede açılmadıysa ve sürüklemediyse: hiçbir şey (iptal)
            self._pinch_kilit = None

        if self._pinch:
            if not self._surukluyor and t - self._pinch_bas >= self.a.surukleme_suresi:
                self._surukluyor = True
                cikti.olaylar.append(("basili_tut", self._pinch_kilit))
            if self._surukluyor:
                cikti.jest = "surukleme"
                return self._bitir(cikti, t, avuc, imlec)
            cikti.jest = "tik"
            return self._bitir(cikti, t, avuc, self._pinch_kilit)

        # --- Derinlik itmesi: eli kameraya doğru hızla it → tıkla ---
        if self.a.itme_aktif:
            if not self._itiliyor:
                eski = [a for zt, a, _ in self._gecmis if t - zt <= self.a.itme_pencere]
                en_kucuk = min(eski) if eski else avuc
                if derinlik >= self.a.itme_orani and (avuc - en_kucuk) >= self.a.itme_artis * self._taban \
                        and t - self._son_itme >= self.a.itme_bekleme:
                    self._itiliyor = True
                    self._itme_bas = t
                    self._son_itme = t
                    kilit = self._gecmisten(t, self.a.itme_pencere) or imlec
                    cikti.olaylar.append(("tikla", kilit))
                    cikti.jest = "itme"
                    return self._bitir(cikti, t, avuc, kilit)
            else:
                if derinlik <= self.a.itme_birak_orani or t - self._itme_bas > 1.5:
                    self._itiliyor = False
                    if t - self._itme_bas > 1.5:
                        self._taban = avuc           # kullanıcı gerçekten yaklaştı: yeni normal
                else:
                    cikti.jest = "itme"
                    return self._bitir(cikti, t, avuc, None)   # el geri çekilirken imleç kaymasın

        self._taban_guncelle(avuc)
        cikti.jest = "imlec"
        return self._bitir(cikti, t, avuc, imlec)

    # ------------------------------------------------------------------

    def _taban_guncelle(self, avuc: float) -> None:
        if self._taban is None:
            self._taban = avuc
        elif not self._itiliyor:
            self._taban += (avuc - self._taban) * self.a.taban_uyum

    def _bitir(self, cikti: ElCikti, t: float, avuc: float,
               imlec: Optional[tuple[float, float]]) -> ElCikti:
        cikti.imlec = imlec
        if imlec is not None:
            self._son_imlec = imlec
        self._gecmis.append((t, avuc, imlec))
        return cikti

    def _el_yok(self) -> ElCikti:
        cikti = ElCikti(jest="yok")
        if self._surukluyor:
            cikti.olaylar.append(("birak", None))   # el kadrajdan çıktı: fareyi basılı bırakma
        self._pinch = self._surukluyor = self._sag_pinch = self._itiliyor = False
        self._kaydirma_y = None
        self._bozkurt_bas = None
        self._gecmis.clear()
        self._ofset = (0.0, 0.0)
        self._kavrama_bekliyor = False
        return cikti
