# -*- coding: utf-8 -*-
"""
=============================================================================
ADAPTERS / BRAIN / TOOLS — Komutları Dil Modeline Araç Olarak Açar
=============================================================================
Model hiçbir şeyi KENDİSİ çalıştırmaz. Sadece "şu aracı şu parametreyle
çağır" der; bu modül o isteği mevcut tipli Command/Query nesnesine çevirir.
Böylece güvenlik ve davranış tamamen senin handler'larında kalır.

Yeni araç eklemek için `_TOOLS` listesine bir `_Tool` ekle — başka yere
dokunmana gerek yok.
=============================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from irle.domain.commands import (
    CancelAllTimers, CancelShutdown, ClearClipboard, CloseApplication, CreateFolder,
    CreateNote, DeleteNote, KillProcess, LockComputer, MediaControl, MuteVolume,
    OpenApplication, ReadClipboard, RestartComputer, ScheduleCommand, SearchFile,
    SearchWeb, SetBrightness, SetVolume, ShutdownComputer, TakeScreenshot, WindowControl,
)
from irle.domain.queries import (
    GetBatteryStatus, GetCurrentTime, GetNetworkStatus, GetSystemInfo, ListNotes,
)


@dataclass(frozen=True)
class _Tool:
    name: str
    description: str
    parameters: dict
    build: Callable[[dict], Any]
    dangerous: bool = False


def _obj(props: dict | None = None, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props or {}, "required": required or []}


def _int(v: Any) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def _clamp(v: Optional[int], lo: int = 0, hi: int = 100) -> Optional[int]:
    return None if v is None else max(lo, min(hi, v))


def _level_or_delta(cls: type, args: dict) -> Any:
    level = _clamp(_int(args.get("seviye")))
    delta = _int(args.get("degisim"))
    if level is not None:
        return cls(level=level)
    if delta is not None and delta != 0:
        return cls(delta=max(-100, min(100, delta)))
    raise ValueError("seviye veya degisim verilmeli")


def _str(args: dict, key: str) -> str:
    val = str(args.get(key, "") or "").strip()
    if not val:
        raise ValueError(f"'{key}' boş olamaz")
    return val


def _schedule(args: dict) -> ScheduleCommand:
    saniye = (_int(args.get("dakika")) or 0) * 60 + (_int(args.get("saniye")) or 0) \
        + (_int(args.get("saat")) or 0) * 3600
    if saniye <= 0:
        raise ValueError("süre (dakika/saniye/saat) verilmeli")
    return ScheduleCommand(delay_seconds=min(saniye, 24 * 3600), inner_command_text=_str(args, "istek"))


_WINDOW_ACTIONS = {"one_getir": "focus", "tam_ekran": "maximize", "kucult": "minimize", "kapat": "close"}

_MEDIA_ACTIONS = {"oynat_duraklat": "play_pause", "sonraki": "next", "onceki": "previous", "durdur": "stop"}
_SYS_TOPICS = ("cpu", "ram", "disk", "gpu")


_TOOLS: list[_Tool] = [
    # --- Uygulamalar -------------------------------------------------------
    _Tool("uygulama_ac", "Bilgisayarda bir uygulama açar (chrome, spotify, discord, notepad, vscode...).",
          _obj({"ad": {"type": "string", "description": "Uygulamanın adı"}}, ["ad"]),
          lambda a: OpenApplication(name=_str(a, "ad"))),
    _Tool("uygulama_kapat", "Açık bir uygulamayı kapatır.",
          _obj({"ad": {"type": "string"}}, ["ad"]),
          lambda a: CloseApplication(name=_str(a, "ad"))),

    _Tool("pencere_kontrol", "Açık bir pencereyi öne getirir, tam ekran yapar, küçültür veya kapatır.",
          _obj({"ad": {"type": "string", "description": "Pencere başlığında geçen ad"},
                "islem": {"type": "string", "enum": list(_WINDOW_ACTIONS)}}, ["ad", "islem"]),
          lambda a: WindowControl(app_name=_str(a, "ad"), action=_WINDOW_ACTIONS[_str(a, "islem")])),
    _Tool("islem_sonlandir", "Donmuş/yanıt vermeyen bir programı zorla kapatır (ör. chrome, spotify).",
          _obj({"ad": {"type": "string", "description": "Program adı"}}, ["ad"]),
          lambda a: KillProcess(process_name=_str(a, "ad"))),

    # --- Zamanlayıcı / hatırlatıcı ---------------------------------------
    _Tool("zamanlayici_kur",
          "Belirli bir süre sonra bir şey yapar ya da hatırlatır. 'istek' ya bir komut cümlesi "
          "('müziği durdur', 'bilgisayarı kilitle') ya da hatırlatma metni ('çayı hatırlat') olur.",
          _obj({"dakika": {"type": "integer"}, "saniye": {"type": "integer"}, "saat": {"type": "integer"},
                "istek": {"type": "string"}}, ["istek"]),
          _schedule),
    _Tool("zamanlayicilari_iptal", "Kurulu tüm zamanlayıcı ve hatırlatıcıları iptal eder.", _obj(),
          lambda a: CancelAllTimers()),

    # --- Ses / parlaklık / medya ------------------------------------------
    _Tool("ses_ayarla", "Sistem sesini ayarlar. Ya 'seviye' (0-100, mutlak) ya da 'degisim' "
                        "(+/- göreli; 'biraz' ≈ 10, 'çok' ≈ 30) ver.",
          _obj({"seviye": {"type": "integer"}, "degisim": {"type": "integer"}}),
          lambda a: _level_or_delta(SetVolume, a)),
    _Tool("sesi_sustur", "Sesi tamamen kapatır ya da susturmayı geri alır.", _obj(),
          lambda a: MuteVolume()),
    _Tool("parlaklik_ayarla", "Ekran parlaklığını ayarlar. 'seviye' (0-100) ya da 'degisim' (+/-).",
          _obj({"seviye": {"type": "integer"}, "degisim": {"type": "integer"}}),
          lambda a: _level_or_delta(SetBrightness, a)),
    _Tool("medya_kontrol", "Çalan müzik/videoyu kontrol eder.",
          _obj({"islem": {"type": "string", "enum": list(_MEDIA_ACTIONS)}}, ["islem"]),
          lambda a: MediaControl(action=_MEDIA_ACTIONS[_str(a, "islem")])),

    # --- Notlar ------------------------------------------------------------
    _Tool("not_al", "Kullanıcı için bir not kaydeder.",
          _obj({"metin": {"type": "string"}}, ["metin"]),
          lambda a: CreateNote(text=_str(a, "metin"))),
    _Tool("notlari_oku", "Kayıtlı son notları getirir.",
          _obj({"adet": {"type": "integer", "description": "Kaç not (varsayılan 3)"}}),
          lambda a: ListNotes(limit=_clamp(_int(a.get("adet")), 1, 20) or 3)),
    _Tool("not_sil", "Notu siler: 'son' sadece son notu, 'hepsi' tüm notları.",
          _obj({"kapsam": {"type": "string", "enum": ["son", "hepsi"]}}, ["kapsam"]),
          lambda a: DeleteNote(mode="all" if a.get("kapsam") == "hepsi" else "last")),

    # --- Bilgi -------------------------------------------------------------
    _Tool("saat_tarih", "Şu anki saati ve tarihi öğrenir.", _obj(), lambda a: GetCurrentTime()),
    _Tool("pil_durumu", "Pil yüzdesini ve şarj durumunu öğrenir.", _obj(), lambda a: GetBatteryStatus()),
    _Tool("sistem_bilgisi", "İşlemci, RAM, disk kullanımını öğrenir.",
          _obj({"konular": {"type": "array", "items": {"type": "string", "enum": list(_SYS_TOPICS)}}}),
          lambda a: GetSystemInfo(topics=tuple(t for t in (a.get("konular") or []) if t in _SYS_TOPICS))),
    _Tool("ag_durumu", "IP adresini ve isteğe bağlı internet gecikmesini öğrenir.",
          _obj({"ping": {"type": "boolean"}}),
          lambda a: GetNetworkStatus(include_ping=bool(a.get("ping")))),

    # --- Web / dosya / ekran ----------------------------------------------
    _Tool("web_ara", "Tarayıcıda Google araması açar.",
          _obj({"sorgu": {"type": "string"}}, ["sorgu"]),
          lambda a: SearchWeb(query=_str(a, "sorgu"))),
    _Tool("dosya_ara", "Masaüstünde dosya arar.",
          _obj({"terim": {"type": "string"}}, ["terim"]),
          lambda a: SearchFile(term=_str(a, "terim"))),
    _Tool("klasor_olustur", "Masaüstünde yeni klasör oluşturur.",
          _obj({"ad": {"type": "string"}}, ["ad"]),
          lambda a: CreateFolder(name=_str(a, "ad"))),
    _Tool("ekran_goruntusu", "Ekran görüntüsü alıp kaydeder.", _obj(), lambda a: TakeScreenshot()),
    _Tool("pano_oku", "Panoya kopyalanmış metni okur.", _obj(), lambda a: ReadClipboard()),
    _Tool("pano_temizle", "Panoyu temizler.", _obj(), lambda a: ClearClipboard()),

    # --- Sistem gücü (tehlikeli: sadece açık istekle) ------------------------
    _Tool("bilgisayari_kilitle", "Ekranı kilitler.", _obj(), lambda a: LockComputer()),
    _Tool("bilgisayari_kapat", "Bilgisayarı kapatır. SADECE kullanıcı açıkça kapatmak isterse.",
          _obj({"gecikme_saniye": {"type": "integer", "description": "Varsayılan 60"}}),
          lambda a: ShutdownComputer(delay_seconds=_clamp(_int(a.get("gecikme_saniye")), 10, 7200) or 60),
          dangerous=True),
    _Tool("yeniden_baslat", "Bilgisayarı yeniden başlatır. SADECE açık istekle.",
          _obj({"gecikme_saniye": {"type": "integer"}}),
          lambda a: RestartComputer(delay_seconds=_clamp(_int(a.get("gecikme_saniye")), 10, 7200) or 60),
          dangerous=True),
    _Tool("kapatmayi_iptal", "Planlanmış kapatma/yeniden başlatmayı iptal eder.", _obj(),
          lambda a: CancelShutdown()),
]

_BY_NAME = {t.name: t for t in _TOOLS}


def tool_specs() -> list[dict]:
    """OpenAI 'tools' biçiminde araç listesi."""
    return [
        {"type": "function",
         "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
        for t in _TOOLS
    ]


def tool_names() -> list[str]:
    return [t.name for t in _TOOLS]


def build_command(name: str, arguments: dict) -> Any:
    """Araç çağrısını tipli Command/Query'ye çevirir. Hatalıysa ValueError."""
    tool = _BY_NAME.get(name)
    if tool is None:
        raise ValueError(f"Bilinmeyen araç: {name}")
    try:
        return tool.build(arguments or {})
    except (KeyError, TypeError) as exc:
        raise ValueError(f"{name} için geçersiz parametre: {exc}") from exc


def is_dangerous(name: str) -> bool:
    tool = _BY_NAME.get(name)
    return bool(tool and tool.dangerous)
