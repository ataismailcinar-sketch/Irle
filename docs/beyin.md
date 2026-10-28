# İrle Beyni — Kurulum ve Çalışma Mantığı

## 5 dakikada kurulum

**En kolayı:** klasördeki `Kurulum.bat`'a çift tıkla. Paketleri kurar, `.env`'i oluşturur, Groq anahtarını
sorar, Ollama'yı (istersen) kurup modeli çeker, Whisper modelini ve Piper sesini indirir, testleri çalıştırır.
Her şeyi `kurulum_log.txt`'ye yazar. Elle yapmak istersen:

1. **Ollama (yerel, çevrimdışı beyin)**
   - https://ollama.com → Windows sürümünü indir, kur.
   - Terminal: `ollama pull qwen2.5:7b`
     (yavaş gelirse: `ollama pull qwen2.5:3b` ve `.env` içinde `IRLE_OLLAMA_MODEL=qwen2.5:3b`)
2. **Groq (ücretsiz bulut beyin, internet varken)**
   - https://console.groq.com → Google ile giriş → *API Keys* → *Create API Key*.
   - Kredi kartı istemez. Ücretsiz katman günde ~1000 istek veriyor (llama-3.3-70b).
3. `env_ornek.txt` dosyasını `.env` adıyla kopyala (terminalde: `copy env_ornek.txt .env`), `GROQ_API_KEY=` satırına anahtarı yapıştır.
4. `Irle_Baslat.bat`

Konsolda şunu görmelisin:
`🧠 Beyin hazır (hibrit): groq:llama-3.3-70b-versatile → ollama:qwen2.5:7b`

## Bir cümle nereye gider?

```
"İrle, ..."  ──(uyandırma açıksa)──►  1. ANLAMA MOTORU  ──emin──►  komut + üsluba uygun cevap
                                          │ emin değil / sohbet / bilgi sorusu
                                          ▼
                                       2. BEYİN  Groq → Ollama
                                          │ ulaşılamadı (internet yok, Ollama kapalı)
                                          ▼
                                       3. YEDEK  anlama motorunun tahmini → hazır sohbet
                                                 cevabı → eski regex → "anlamadım"
```

| Cümle | Kim halleder | Not |
|---|---|---|
| "abi şu müziği biraz alçalt da kafam şişti" | Anlama motoru | uzun ama net → model beklenmez |
| "sesi yüzde kırk beş yap", "sesi 30'a çek" | Anlama motoru | sayı kelimeleri, "-e/-a" = hedef seviye |
| "kroma aç", "not defterini aç", "youtube aç" | Anlama motoru | bulanık ad eşleşmesi, siteler tarayıcıda |
| "spotify'ı aç ve sesi kıs" | Anlama motoru | net bileşik komut |
| "biraz daha", "geri al", "onu kapat", "ne dedin" | Anlama motoru | son 3 dakikanın bağlamı |
| "5 dakika sonra çayı hatırlat" | Anlama motoru | zamanlayıcı / hatırlatıcı |
| "sesi kısma" | Anlama motoru | olumsuz → hiçbir şey yapmaz |
| "selam", "teşekkürler", "şaka yap" | Beyin (yoksa hazır cevap) | |
| "bugün kendimi yorgun hissediyorum" | Beyin | anlama motoru bilmiyor |
| "photoshop aç" (bilinmeyen ad) | Beyin (yoksa yine dener) | güven düşük |

Konsolda her cümle için hangi yolun seçildiği görünür:
`⚡ [nlu:ses_azaldi | samimi] 'kanka sesi kıs' → SetVolume(delta=-15)` ya da `🧠 [groq | ...]`.

Beyin sırası: **Groq → Ollama**. Groq'a ulaşılamazsa (internet yok, günlük kota doldu)
2 dakika boyunca hiç denenmez, doğrudan Ollama'ya gidilir; sonra tekrar denenir.

## Kulak: hibrit konuşma tanıma

Sıra: **Groq Whisper → yerel Whisper → Google**.

- **Groq Whisper** (`whisper-large-v3-turbo`): `GROQ_API_KEY` ile otomatik açılır, ücretsiz, Türkçesi çok iyi.
- **Yerel Whisper** (faster-whisper): tamamen çevrimdışı. Ekran kartını dener, olmazsa işlemciye geçer.
  Model ilk kullanımda indirilir; **köye gitmeden önce** internet varken bir kez çalıştır:
  `python tools/hazirlik_kontrol.py --indir`
- **Google**: eski davranış, son yedek.

Bir servis "konuşma yok" derse diğerlerine sorulmaz (her gürültü üç servise gitmesin).
Sadece servis çalışmıyorsa (internet yok, kota doldu) sıradakine geçilir ve bozuk olan 2 dakika dinlenmeye alınır.

Whisper'ın sessizlikte uydurduğu metinler ("Altyazı M.K.", "İzlediğiniz için teşekkürler",
"Abone olmayı unutmayın"...) süzülür. 0,5 saniyeden kısa sesler (tıkırtı, öksürük) hiç gönderilmez.

## Ses: doğal Türkçe (Piper)

İrle artık Windows'un robotik sesi yerine **Piper** ile konuşur: nöral, doğal Türkçe, tamamen çevrimdışı.
Ses dosyası (~60 MB) `data/sesler/` klasörüne bir kez indirilir (`--indir`). Varsayılan ses
`tr_TR-fahrettin-medium`; indirilemezse `fettah` ve `dfki` denenir. Ses dosyası yoksa ya da Piper
kurulu değilse otomatik olarak Windows sesine (Türkçe "Tolga" yüklüyse o) dönülür.

Uzun cevaplar cümle cümle üretilip çalınır, ilk cümle hemen duyulur. Okumadan önce metin temizlenir:
emoji, markdown ve linkler okunmaz; "%45" → "yüzde 45", "12:08" → "on iki sekiz", "GB" → "gigabayt".

Hız için `.env` → `IRLE_PIPER_HIZ=1.15` gibi.

## Yüz: Kıpçak maskeli kafa

Arayüzün üstünde, 13. yüzyıl Kıpçak savaşçılarının yüz maskeli miğferlerinden esinlenen ve
tamamen kodla çizilen (`modules/gui_avatar.py`, resim dosyası yok) animasyonlu bir kafa var.
Etrafında Orhun yazısıyla "Tengri · Türk · Bilge · İrle" yazan bir halka döner.

| Durum | Renk | Ne olur |
|---|---|---|
| Dinliyor | mavi | sakin nefes, ara sıra göz kırpar |
| Duyuyor | turkuaz | mikrofon konuşma yakaladı, gözler parlar |
| Düşünüyor | mor | halka hızlanır, harfler sırayla yanar |
| Konuşuyor | altın | ağız çalan sesin gerçek şiddetiyle açılıp kapanır (Piper), hale onunla dalgalanır |
| Hata | kırmızı | kısa titreşim, sonra eski haline döner |
| Bekliyor | soluk altın | sessiz mod |

Dudak senkronu: Piper her cümleyi çalmadan önce sesin şiddet eğrisini (saniyede 40 ölçüm)
`src/irle/infra/ses_seviyesi.py`'ye yazar, yüz her karede o anı okur. Windows sesinde (pyttsx3)
ses verisine erişilemediği için ağız sabit bir konuşma ritmiyle oynar.

Göktürk harfleri Windows'ta "Segoe UI Historic" fontuyla çizilir (Windows 10/11'de hazır gelir).
Font yoksa harflerin yerine rün çentikleri çizilir.

## El ile fare kontrolü

Kamera elini izler; mantık `src/irle/adapters/vision/el_jestleri.py`'de (kamerasız test edilebilir).

| Hareket | Ne yapar |
|---|---|
| ✋ Açık el, hareket et | İmleç. Avucun ortası izlenir; parmakların oynasa da imleç kaymaz |
| 👌 Başparmak + işaret, kısa | Tıkla (birleştirmeden hemen önceki konuma) |
| 👌 Başparmak + işaret, 0,4 sn+ tut | Sürükle; parmakları açınca bırak |
| 🤌 Başparmak + orta parmak | Sağ tık |
| ✌️ İki parmak (işaret + orta), yukarı/aşağı | Kaydır (bu sırada imleç durur) |
| ✊ Yumruk | İmleç donar; elini başka yere götür, açınca imleç kaldığı yerden devam eder |
| 👉 Eli kameraya doğru hızla it | Tıkla (derinlik) |
| 🤘 Bozkurt, 1 sn tut | El kontrolünü aç / beklemeye al |

**Derinlik nasıl ölçülüyor?** MediaPipe'ın `z` değeri bileğe göre görelidir ve kameraya uzaklığı
göstermez (eski "itme" tıklamasının çalışmamasının sebebi buydu). Şimdi avucun görüntüdeki
büyüklüğü ölçülüyor: el yaklaştıkça büyür. ~0,35 sn içinde %15'ten fazla büyürse "itme" sayılır.
Yavaşça yaklaşmak tıklamaz, çünkü normal mesafe ("taban") yavaşça uyum sağlar. Kamera penceresinin
sağındaki **DERİNLİK** çubuğu bunu canlı gösterir; kırmızı çizgiyi geçince tıklar.

İmleç alanı da mesafeye uyar: elin uzaktayken küçük bir hareket yeter. Arayüzdeki **⊕ Kalibrasyon**
butonuna basıp elini 3 saniye normal kullanma mesafende tutarsan alan sana göre ayarlanır.

Eskiden aynı anda üç tıklama yöntemi açıktı; biri "elini 0,7 sn sabit tut" idi ve kendiliğinden
tıklıyordu. Hızlı yukarı-aşağı hareket de kaydırma sayılıyordu. İkisi de kaldırıldı.

## Hazırlık kontrolü

`python tools/hazirlik_kontrol.py` her şeyi tek seferde kontrol eder: paketler, `.env`, Groq anahtarı,
Ollama ve modeli, yerel Whisper modeli diskte mi, Piper Türkçe sesi, mikrofon.
`--indir` ile eksik Whisper modelini ve Piper sesini indirir (internet varken bir kez). Sonunda yapılacaklar listesi verir.

## Uyandırma kelimesi (opsiyonel)

`.env` içine `IRLE_UYANDIRMA=irle` yazarsan sadece "İrle ..." diye başlayan cümleler işlenir
(televizyon, müzik, yan odadaki sohbet komut sanılmaz). İrle cevap verdikten sonra 20 saniye
boyunca kelimeyi tekrar söylemeden devam edebilirsin ("İrle sesi kıs" → "biraz daha").
Sadece "İrle" dersen "Efendim?" der. Konuşma tanıma hataları (ırle, erle, irla...) tolere edilir.

## Yankı kilidi ve araya girme

İrle konuşurken normal dinleme kapalıdır; böylece kendi sesini komut sanıp kendi kendine
konuşmaz. Konuşma bittikten 0,6 saniye sonra dinleme devam eder.

Ama **araya girebilirsin**:
- "dur", "sus", "yeter", "tamam tamam", "İrle dur", "bekle bir saniye" → İrle hemen susar,
  sıradaki cümleleri de atlar.
- "İrle, sesi kıs" (uyandırma kelimesiyle yeni komut) → susar ve yeni komutu yapar.

Yankıyı kullanıcıdan ayırmak için üç önlem var:
1. Sadece İrle'nin kelime/cümle aralarındaki sessiz anlarda da mikrofonda güçlü ses varsa
   tanımaya gönderilir (Piper'ın çalan sesinin şiddeti bilindiği için). Windows sesinde bu
   bilinmediğinden çok daha yüksek bir ses eşiği kullanılır.
2. Tanınan metin İrle'nin o an söylediğine benziyorsa yankı sayılır, atılır.
3. "Dur" gibi kelimeler sadece kısa bir cümlede (en fazla 4 kelime) geçerlidir.

İki kesme denemesi arasında en az 2 saniye beklenir (Groq kotası boşa gitmesin).
Kapatmak için: `.env` → `IRLE_KESME=false`. Kulaklık kullanıyorsan en iyi böyle çalışır;
hoparlörle de çalışır ama çok yüksek seste yankı süzgeci zorlanabilir.

## Kişilik: kullanıcıya uyar

`src/irle/adapters/brain/persona.py` son 8 cümlene bakar ve şu sinyalleri çıkarır:
samimiyet (kanka/abi/ya ↔ lütfen/rica), "siz" hitabı, argo, sabırsızlık (of, yeter, !),
espri (haha, xd), cümle uzunluğu, sohbet isteği.

Bu sadece tonu değil **davranışı** da değiştirir:

- Kısa emirler ("ses kıs") → soru sormaz, hemen yapar, 2-3 kelimeyle cevap verir.
- Kanka üslubu → samimi konuşur, senin hitaplarını geri kullanır.
- "Yapar mısınız lütfen" → "siz" der, riskli işlerde kibarca onay ister.
- Gergin ("of yine çalışmıyor") → espri yapmaz, özür dileyip uzatmaz, hemen çözer.
- Sohbetçi / uzun anlatan → işten sonra kısa yorum veya soru ekler.

Konsoldaki `🧠 [groq | samimi, kısa-net]` etiketi o an seni nasıl algıladığını gösterir.

## Güvenlik

- Model hiçbir şeyi doğrudan çalıştırmaz; sadece `tools.py`'deki araçları çağırabilir,
  bunlar da senin tipli komutlarına (`SetVolume`, `CreateNote`...) çevrilir.
- Bilgisayarı kapatma / yeniden başlatma, cümlede "kapat / yeniden başlat" açıkça geçmiyorsa
  model istese bile çalıştırılmaz.
- Groq'a giden şey sadece konuştuğun cümleler ve araç sonuçlarıdır. Bunu istemediğin anlarda
  `.env` içinde `IRLE_BEYIN_MODU=yerel` yap: her şey bilgisayarında kalır.

## Yeni yetenek eklemek

1. `domain/commands.py`'ye komutu, `handlers/`'a handler'ı ekle, `command_registry.py`'de kaydet.
2. `adapters/brain/tools.py` → `_TOOLS` listesine bir `_Tool(...)` satırı ekle (beyin kullanır).
3. İstersen `adapters/intent/nlu.py`'ye bir niyet ekle (çevrimdışı, anında çalışsın diye) ve
   `adapters/intent/yanitlar.py`'ye dört ağızlı (kisa/notr/samimi/resmi) bir cevap kategorisi.

Yeni uygulama ya da site adı eklemek için `nlu.py` → `_VARSAYILAN_UYGULAMALAR` /
`_VARSAYILAN_SITELER` sözlüğüne takma adlarıyla birlikte ekle (ör. "spotifay" gibi telaffuzlar).
