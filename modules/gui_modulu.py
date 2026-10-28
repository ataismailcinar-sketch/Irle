"""
=============================================================================
GUI MODÜLÜ — Görsel Arayüz Katmanı (V2.1)
=============================================================================
Bu modülün TEK sorumluluğu:
    1. Tüm sistem event'lerini dinlemek.
    2. Konuşmaları ve sistem durumunu ekranda göstermek.
    3. Ana thread'de çalışmak (tkinter zorunlu kılar).
    4. v2.1: Telefon Kontrolcü QR paneli eklendi.

ÖNEMLİ: tkinter SADECE ana thread'de çalışır.
Bu nedenle modül, ana thread'i kendisi yönetir.
main.py'de bu modülün .mainloop() çağrısı en sona konulmalıdır.

Tasarım:
    ┌─────────────────────────────────┐
    │   IRLE — AI Asistan     🎙️   │
    ├─────────────────────────────────┤
    │  💬 Konuşma Geçmişi           │
    │  > Kullanıcı: not deft...      │
    │  > Asistan: Açıyorum...        │
    ├─────────────────────────────────┤
    │  📊 Sistem Durumu              │
    │  Events: 5 | TTS: Hazır        │
    └─────────────────────────────────┘
=============================================================================
"""

import tkinter as tk
from tkinter import scrolledtext
import threading
import queue
import logging
from datetime import datetime
import config
from modules.gui_avatar import KipcakMaske

logger = logging.getLogger("GuiModulu")

# --- Renk Paleti (Koyu Tema) -------------------------------------------------
RENK = {
    "arkaplan":     "#0f1117",
    "panel":        "#1a1d27",
    "kenar":        "#2a2d3e",
    "kullanici":    "#4f8ef7",
    "asistan":      "#a78bfa",
    "sistem":       "#34d399",
    "uyari":        "#fbbf24",
    "hata":         "#f87171",
    "metin":        "#e2e8f0",
    "metin_soluk":  "#64748b",
    "vurgu":        "#6366f1",
}


class GuiModulu:
    """
    Sistemi görsel olarak izleyen tkinter arayüz modülü.
    """

    def __init__(self, event_bus, telefon_kontrolcu=None):
        self.bus = event_bus
        self._telefon = telefon_kontrolcu

        # GUI güncellemeleri event thread'lerinden ana thread'e
        # bu kuyruk aracılığıyla iletilir (thread-safe).
        self._ui_kuyrugu: queue.Queue = queue.Queue()

        # Event sayaçları
        self._event_sayaci = 0

        # Tüm önemli event'lere abone ol
        self.bus.subscribe("ses_algilandi",       self._ses_algilandi_ui)
        self.bus.subscribe("asistan_yanit_verdi", self._asistan_yaniti_ui)
        self.bus.subscribe("uygulama_ac",         self._uygulama_ac_ui)
        self.bus.subscribe("tts_konuş",           self._tts_konusuyor_ui)
        self.bus.subscribe("tts_bitti",           self._tts_bitti_ui)
        self.bus.subscribe("bellek_kaydet",       self._bellek_kaydedildi_ui)
        self.bus.subscribe("vision_el_modu_toggle", self._el_modu_toggle_ui)
        # Avatar durumları
        self.bus.subscribe("konusma_basladi",     lambda m: self._avatar_durum("duyuyor"))
        self.bus.subscribe("konusma_bitti",       lambda m: self._avatar_durum("dinliyor"))
        self.bus.subscribe("komut_basarisiz",     lambda m: self._avatar_durum("hata"))
        self._avatar = None

        # tkinter penceresi (baslat() içinde oluşturulur)
        self._pencere = None
        self._qr_pencere = None

    def baslat(self) -> None:
        """
        GUI'yi ana thread'de başlatır.
        Bu metot BLOKLAR — mainloop() çalıştıkça devam etmez.
        main.py'de en SON çağrılmalıdır.
        """
        self._pencere_olustur()
        logger.info("GUI Modülü başlatıldı.")

        # Kuyruktan gelen UI güncellemelerini periyodik olarak uygula
        self._pencere.after(100, self._ui_kuyruğunu_isle)

        # Ana döngüyü başlat (bu noktadan sonra sistem event-driven çalışır)
        self._pencere.mainloop()

    def durdur(self) -> None:
        """Pencereyi kapat."""
        if self._pencere:
            try:
                self._pencere.quit()
            except Exception:
                pass
        logger.info("GUI Modülü durduruldu.")

    # -------------------------------------------------------------------------
    #  PENCERE KURULUMU
    # -------------------------------------------------------------------------

    def _pencere_olustur(self) -> None:
        """Ana pencereyi ve tüm widget'ları oluşturur."""
        self._pencere = tk.Tk()
        self._pencere.title("İrle")
        self._pencere.geometry("760x820")
        self._pencere.minsize(560, 640)
        self._pencere.configure(bg=RENK["arkaplan"])
        self._pencere.resizable(True, True)
        self._pencere.protocol("WM_DELETE_WINDOW", self._kapat)

        # Grid layout: başlık / Kıpçak maskeli kafa / sohbet / durum çubuğu
        self._pencere.columnconfigure(0, weight=1)
        self._pencere.rowconfigure(2, weight=1)

        self._baslik_olustur()
        self._avatar_olustur()
        self._sohbet_alani_olustur()
        self._durum_cubugu_olustur()
        if getattr(config, "SESSİZ_MOD", False):
            self._avatar_durum("bekliyor")

        # İlk karşılama mesajı
        self._log_ekle("sistem", "⚡ İrle başlatıldı. Mikrofon hazır.")
        if self._telefon:
            url = self._telefon.get_url()
            self._log_ekle("sistem", f"📱 Telefon Kontrolcü → {url}")

    def _baslik_olustur(self) -> None:
        """Üst başlık paneli."""
        baslik_frame = tk.Frame(self._pencere, bg=RENK["panel"], pady=12)
        baslik_frame.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        baslik_frame.columnconfigure(0, weight=1)

        baslik = tk.Label(
            baslik_frame,
            text="◈  İ R L E  ◈",
            font=("Segoe UI", 15, "bold"),
            fg=RENK["vurgu"],
            bg=RENK["panel"],
        )
        baslik.grid(row=0, column=0)

        self._durum_etiketi = tk.Label(
            baslik_frame,
            text="🎙️  Dinleniyor...",
            font=("Segoe UI", 9),
            fg=RENK["sistem"],
            bg=RENK["panel"],
        )
        self._durum_etiketi.grid(row=1, column=0, pady=(2, 0))

    def _avatar_olustur(self) -> None:
        """Kıpçak maskeli animasyonlu kafa."""
        frame = tk.Frame(self._pencere, bg=RENK["arkaplan"])
        frame.grid(row=1, column=0, pady=(8, 0))
        self._avatar = KipcakMaske(frame, boyut=280, arkaplan=RENK["arkaplan"])
        self._avatar.pack()

    def _avatar_durum(self, ad: str) -> None:
        """Thread-safe: avatar durumunu ana thread'de değiştir."""
        if ad in ("dinliyor",) and getattr(config, "SESSİZ_MOD", False):
            ad = "bekliyor"
        self._ui_kuyrugu.put(lambda a=ad: self._avatar and self._avatar.durum(a))

    def _sohbet_alani_olustur(self) -> None:
        """Mesajların gösterildiği kaydırılabilir metin alanı."""
        frame = tk.Frame(self._pencere, bg=RENK["arkaplan"])
        frame.grid(row=2, column=0, sticky="nsew", padx=16, pady=10)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self._sohbet = scrolledtext.ScrolledText(
            frame,
            wrap=tk.WORD,
            font=("Consolas", 10),
            bg=RENK["panel"],
            fg=RENK["metin"],
            insertbackground=RENK["metin"],
            borderwidth=0,
            highlightthickness=1,
            highlightcolor=RENK["kenar"],
            highlightbackground=RENK["kenar"],
            padx=12,
            pady=10,
            state="disabled",  # Kullanıcı yazmasın
        )
        self._sohbet.grid(row=0, column=0, sticky="nsew")

        # Renkli metin etiketleri
        self._sohbet.tag_configure("kullanici", foreground=RENK["kullanici"], font=("Consolas", 10, "bold"))
        self._sohbet.tag_configure("asistan",   foreground=RENK["asistan"],  font=("Consolas", 10, "bold"))
        self._sohbet.tag_configure("sistem",    foreground=RENK["sistem"],   font=("Consolas", 9))
        self._sohbet.tag_configure("uyari",     foreground=RENK["uyari"],    font=("Consolas", 9))
        self._sohbet.tag_configure("hata",      foreground=RENK["hata"],     font=("Consolas", 9))
        self._sohbet.tag_configure("timestamp", foreground=RENK["metin_soluk"], font=("Consolas", 8))

    def _durum_cubugu_olustur(self) -> None:
        """Alt durum çubuğu."""
        alt_frame = tk.Frame(self._pencere, bg=RENK["panel"], pady=6)
        alt_frame.grid(row=3, column=0, sticky="ew")
        alt_frame.columnconfigure(2, weight=1)

        self._event_etiketi = tk.Label(
            alt_frame,
            text="Events: 0",
            font=("Segoe UI", 8),
            fg=RENK["metin_soluk"],
            bg=RENK["panel"],
            padx=12,
        )
        self._event_etiketi.grid(row=0, column=0, sticky="w")

        self._kalibrasyon_btn = tk.Button(
            alt_frame,
            text="⊕ Kalibrasyon",
            bg=RENK["vurgu"],
            fg="white",
            borderwidth=0,
            padx=10,
            pady=2,
            font=("Segoe UI", 8, "bold"),
            command=self._oto_kalibrasyon_baslat,
            cursor="hand2",
        )
        self._kalibrasyon_btn.grid(row=0, column=1, padx=4)

        # 📱 Telefon Kontrolcü Butonu
        if self._telefon:
            self._telefon_btn = tk.Button(
                alt_frame,
                text="📱 Telefon",
                bg="#312e81",
                fg=RENK["asistan"],
                borderwidth=0,
                padx=10,
                pady=2,
                font=("Segoe UI", 8, "bold"),
                command=self._telefon_qr_goster,
                cursor="hand2",
            )
            self._telefon_btn.grid(row=0, column=2, padx=4)

        self.sessiz_mod_var = tk.BooleanVar(value=getattr(config, "SESSİZ_MOD", False))
        self._sessiz_btn = tk.Checkbutton(
            alt_frame,
            text="🔇 Sessiz",
            variable=self.sessiz_mod_var,
            bg=RENK["panel"],
            fg=RENK["metin_soluk"],
            selectcolor=RENK["kenar"],
            activebackground=RENK["panel"],
            activeforeground=RENK["metin"],
            command=self._sessiz_mod_degisti,
        )
        self._sessiz_btn.grid(row=0, column=3, padx=4)

        # ✋ El Modu Butonu (PC'den açıp kapatmak için)
        self.el_modu_var = tk.BooleanVar(value=True)
        self._el_modu_btn = tk.Checkbutton(
            alt_frame,
            text="✋ El Modu",
            variable=self.el_modu_var,
            bg=RENK["panel"],
            fg=RENK["metin_soluk"],
            selectcolor=RENK["kenar"],
            activebackground=RENK["panel"],
            activeforeground=RENK["metin"],
            command=self._el_modu_degisti,
        )
        self._el_modu_btn.grid(row=0, column=4, padx=4)

        versiyon = tk.Label(
            alt_frame,
            text="İrle v2.5",
            font=("Segoe UI", 8),
            fg=RENK["metin_soluk"],
            bg=RENK["panel"],
            padx=12,
        )
        versiyon.grid(row=0, column=5, sticky="e")

    # -------------------------------------------------------------------------
    #  TELEFON QR KOD PENCERESİ
    # -------------------------------------------------------------------------

    def _telefon_qr_goster(self) -> None:
        """Telefon bağlantısı için QR kodu gösteren popup pencere."""
        if self._qr_pencere and self._qr_pencere.winfo_exists():
            self._qr_pencere.lift()
            return

        self._qr_pencere = tk.Toplevel(self._pencere)
        self._qr_pencere.title("📱 Telefon Kontrolcü")
        self._qr_pencere.configure(bg=RENK["arkaplan"])
        self._qr_pencere.geometry("360x480")
        self._qr_pencere.resizable(False, False)

        # Başlık
        tk.Label(
            self._qr_pencere,
            text="📱  Telefon Kontrolcü",
            font=("Segoe UI", 13, "bold"),
            fg=RENK["asistan"],
            bg=RENK["arkaplan"],
        ).pack(pady=(20, 4))

        url = self._telefon.get_url()
        tk.Label(
            self._qr_pencere,
            text=url,
            font=("Consolas", 11),
            fg=RENK["sistem"],
            bg=RENK["arkaplan"],
        ).pack(pady=(0, 16))

        # QR kod görseli
        try:
            from PIL import Image, ImageTk
            import io
            qr_bytes = self._telefon.get_qr_bytes()
            img = Image.open(io.BytesIO(qr_bytes)).resize((240, 240), Image.NEAREST)
            photo = ImageTk.PhotoImage(img)
            qr_label = tk.Label(
                self._qr_pencere,
                image=photo,
                bg=RENK["arkaplan"],
            )
            qr_label.image = photo  # referans tut
            qr_label.pack(pady=8)
        except Exception as e:
            logger.warning(f"QR görseli gösterilemedi: {e}")
            tk.Label(
                self._qr_pencere,
                text="[QR kodu gösterilemedi\nPillow yüklü değil]",
                font=("Consolas", 10),
                fg=RENK["uyari"],
                bg=RENK["arkaplan"],
            ).pack(pady=20)

        # Bilgi metni
        bilgi = (
            "1. Telefonu aynı WiFi ağına bağla\n"
            "2. Kameranla QR kodu tara veya\n"
            "   tarayıcıda adresi yaz\n"
            "3. Gamepad / Klavye / Mouse seç"
        )
        tk.Label(
            self._qr_pencere,
            text=bilgi,
            font=("Segoe UI", 9),
            fg=RENK["metin_soluk"],
            bg=RENK["arkaplan"],
            justify="center",
        ).pack(pady=(8, 16))

    # -------------------------------------------------------------------------
    #  UI GÜNCELLEME YARDIMCILARI
    # -------------------------------------------------------------------------

    def _ui_kuyruğunu_isle(self) -> None:
        """
        Kuyruktan bekleyen UI güncellemelerini main thread'de uygular.
        100ms'de bir tekrar çağrılır.
        """
        try:
            while True:
                guncelleme = self._ui_kuyrugu.get_nowait()
                guncelleme()
        except queue.Empty:
            pass
        finally:
            if self._pencere:
                self._pencere.after(100, self._ui_kuyruğunu_isle)

    def _log_ekle(self, tur: str, metin: str) -> None:
        """
        Sohbet alanına renkli bir satır ekler.
        Bu metot SADECE ana thread'den çağrılmalıdır.
        """
        self._sohbet.configure(state="normal")

        # Zaman damgası
        zaman = datetime.now().strftime("%H:%M:%S")
        self._sohbet.insert(tk.END, f"[{zaman}] ", "timestamp")

        # Mesaj türüne göre ikon ve etiket
        tur_ekstra = {
            "kullanici": "👤 Sen: ",
            "asistan":   "🤖 İrle: ",
            "sistem":    "⚙️ ",
            "uyari":     "⚠️ ",
            "hata":      "❌ ",
        }
        self._sohbet.insert(tk.END, tur_ekstra.get(tur, ""), tur)
        self._sohbet.insert(tk.END, metin + "\n", tur)

        self._sohbet.configure(state="disabled")
        self._sohbet.see(tk.END)  # En alta kaydır

        # Event sayacını güncelle
        self._event_sayaci += 1
        self._event_etiketi.configure(text=f"Events: {self._event_sayaci}")

    def _durum_guncelle(self, metin: str, renk: str = None) -> None:
        """Başlıktaki durum etiketini günceller."""
        self._durum_etiketi.configure(
            text=metin,
            fg=renk or RENK["sistem"],
        )

    # -------------------------------------------------------------------------
    #  Eylemler
    # -------------------------------------------------------------------------

    def _sessiz_mod_degisti(self):
        yeni_deger = self.sessiz_mod_var.get()
        config.SESSİZ_MOD = yeni_deger
        self._avatar_durum("bekliyor" if yeni_deger else "dinliyor")
        self.bus.publish("bildirim", {"mesaj": f"Sessiz mod {'açıldı' if yeni_deger else 'kapatıldı'}."})

    def _oto_kalibrasyon_baslat(self):
        self.bus.publish("oto_kalibrasyon_istegi", {})

    def _el_modu_degisti(self):
        yeni_deger = self.el_modu_var.get()
        self.bus.publish("vision_el_modu_toggle", {"aktif": yeni_deger})

    def _el_modu_toggle_ui(self, mesaj: dict) -> None:
        data = mesaj.get("data", {})
        aktif = data.get("aktif", True)
        self._ui_kuyrugu.put(lambda: self.el_modu_var.set(aktif))

    # -------------------------------------------------------------------------
    #  EVENT HANDLER'LARI — Thread'lerden kuyruğa ekler
    # -------------------------------------------------------------------------

    def _ses_algilandi_ui(self, mesaj: dict) -> None:
        self._avatar_durum("dusunuyor")
        metin = mesaj["data"].get("metin", "")
        self._ui_kuyrugu.put(lambda m=metin: (
            self._log_ekle("kullanici", m),
            self._durum_guncelle("💭  İşleniyor...", RENK["uyari"]),
        ))

    def _asistan_yaniti_ui(self, mesaj: dict) -> None:
        yanit = mesaj["data"].get("yanit", "")
        if yanit:
            self._ui_kuyrugu.put(lambda y=yanit: (
                self._log_ekle("asistan", y),
                self._durum_guncelle("🎙️  Dinleniyor...", RENK["sistem"]),
            ))

    def _uygulama_ac_ui(self, mesaj: dict) -> None:
        uygulama = mesaj["data"].get("uygulama", "")
        self._ui_kuyrugu.put(lambda u=uygulama:
            self._log_ekle("sistem", f"Uygulama başlatıldı → {u}")
        )

    def _tts_konusuyor_ui(self, mesaj: dict) -> None:
        if not getattr(config, "SESSİZ_MOD", False):
            self._avatar_durum("konusuyor")
        self._ui_kuyrugu.put(lambda:
            self._durum_guncelle("🔊  Konuşuyor...", RENK["asistan"])
        )

    def _tts_bitti_ui(self, mesaj: dict) -> None:
        self._avatar_durum("dinliyor")
        self._ui_kuyrugu.put(lambda:
            self._durum_guncelle("🎙️  Dinleniyor...", RENK["sistem"])
        )

    def _bellek_kaydedildi_ui(self, mesaj: dict) -> None:
        # Bellek kaydı sessizce gerçekleşir — arayüze yansıtmıyoruz
        pass

    def _kapat(self) -> None:
        """Pencere kapatma butonu."""
        if self._qr_pencere:
            try:
                self._qr_pencere.destroy()
            except Exception:
                pass
        self._pencere.quit()
