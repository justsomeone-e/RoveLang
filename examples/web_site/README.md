# Rove WebAssembly (WASM) İnteraktif Web Sitesi

Bu proje, **Rove** sistem programlama dili kullanılarak yazılmış, saf **WebAssembly (`wasm32`)** ikili koduna derlenmiş ve tarayıcıda çalışan interaktif bir web sitesi ve görselleştirme portalıdır.

---

## 🌟 Neler İçerir?

1. **Rove WASM 60 FPS 3D Optik Shader & Çizim Motoru (`std/web`)**:
   - Rove dilindeki `web_canvas_set_blend_mode`, `web_canvas_set_global_alpha`, `web_canvas_draw_glow_circle`, `web_canvas_draw_line` ve `web_canvas_draw_circle` fonksiyonları ile gerçek zamanlı optik parlama (additive bloom), 3D derinlik izdüşümü ve parçacık fiziği.
   - 9 Farklı 3D Görsel & Oyun Modu:
     - **3D Spektrum Işınları (Mod 0)**: 3D Tron zemin ızgarası üzerinde yükselen, neon parlama başlıklı ve yansımalı 24 holografik ses kulesi.
     - **3D Siber Matris Tüneli (Mod 1)**: Sonsuza uzanan 3D perspektif tünelinde kameraya doğru akan beyaz kor başlıklı dijital veri akımları.
     - **3D Kuantum Jiroskop & Güneş Çekirdeği (Mod 2)**: $X, Y, Z$ eksenlerinde bağımsız dönen 3 eşmerkezli 3D halka, yörüngedeki elektronlar ve hacimsel korona ışımalı plazma çekirdeği.
     - **🏓 3D Tron Pong 2.0 (Mod 3)**:
       - 3D Tron kort perspektifi, derinlik çizgileri, lazer sınır rayları ve neon net çizgisi.
       - Hacimsel kuyruklu 3D plazma topu, dönen kalkan halkalı güçlendirici küreler ve 3D derinlikli holografik raketler.
       - **1P & 2P Modu**: Tek klavyede 2 kişilik oyun (P1: `W`/`S`, P2: `Yukarı`/`Aşağı` ok tuşları) veya 3 seviyeli yapay zeka.
     - **🚀 3D Hiperuzay Uzay Koşusu (Mod 4)**: 3D yıldız alanı warp akışı, çift plazma iticili önleyici uzay gemisi, 3D enerji kalkanı küresi, lazer kapıları ve kristal asteroitler.
     - **Shibuya Romantik Havai Fişek Festivali (Mod 5)**: Ay ışığı, sakin yıldız alanı, neon Shibuya silüeti, yağmurla parlayan yaya geçidi, şemsiye altındaki çift ve yumuşak çok halkalı kuyruklara sahip performans dostu havai fişekler.
     - **🌌 3D Kuantum Çekim Tekilliği (Relativistic Kerr Black Hole - Mod 6)**:
       - **3D Bükülen Uzay-Zaman Hunisi**: Genel görelilik simülasyonu — tekilliğe doğru bükülen 12 radyal hat ve 6 uzay-zaman ızgara halkası.
       - **3D Eğimli Yığılma Diski (Accretion Disk)**: 3D perspektifle eğilmiş dönen plazma kuşakları ve Doppler etkisi (maviye kayan ön kenar, kırmızıya kayan arka kenar).
       - **Einstein Kütleçekimsel Mercekleme Yayı (Gravitational Lensing)**: Işığın karadeliğin arkasından bükülerek üstünden görünmesi (Gargantua / Interstellar efekti).
       - **Göreliliksel Kutup Jetleri**: Kutup noktalarından fışkıran lazer huzmeleri ve sarmal parçacıklar.
       - **Olay Ufku & Foton Halkası**: Işığı yutan saf kozmik boşluk ve göz kamaştırıcı beyaz foton çemberi.
       - **32 Kuantum Düğümü**: Gerçek 3D koordinatlarda yörüngede dönen, derinlik izdüşümü ($Z$-depth) ile ön planda parlayan ve lazer ağlarıyla birbirine bağlanan parçacıklar.
       - **Süpernova Şok Dalgası**: Boşluk (`Space`) tuşuna basarak tetiklenen çok renkli kromatik şok dalgası halkaları.
     - **Aurora Plazma Kafesi (Mod 7)**: Üç farklı faz ve derinlikte akan Rove/WASM aurora şeritleri, perspektif ışık zemini ve hareketli iyon parçacıkları.
     - **Derin Uzay Sinir Ağı (Mod 8)**: Paralaks yıldız katmanları, deterministik bağlantı topolojisi ve nefes alan ışık çekirdeğiyle prosedürel neural constellation sahnesi.
   - **⚡ 3D Shader FX & CRT Post-Processing**:
     - Sayfadaki butonla değiştirilebilen ham Canvas, sinematik renk/bloom ve CRT bloom profilleri; fareyi izleyen optik flare, lens vinyeti ve canlı frame-pacing telemetrisi.
2. **🎵 Rove Prosedürel Müzik İstasyonu & Siber DJ Launchpad**:
   - Harici MP3/WAV ses dosyası olmadan, Web Audio API ve Rove WASM ile 100% matematiksel canlı sentezlenen ses motoru!
   - Rove WebAssembly fonksiyonları tarafından hesaplanan melodi frekansları (`music_lead_note`), bas dizilimleri (`music_bass_note`) ve davul vuruşları (`music_drum_beat`).
   - **5 Farklı Prosedürel Parça**:
     1. Cyberpunk Synthwave (128 BPM)
     2. 8-Bit Retro Arcade (140 BPM)
     3. Neon Chillwave (110 BPM)
     4. Tokyo Neon Drift (144 BPM)
     5. Arcade Boss Battle (152 BPM)
   - **Ses Özelleştirme**: Dalga formu seçimi (`sawtooth`, `square`, `triangle`, `sine`) ve tempo çarpanı (`0.75x`, `1.0x`, `1.25x`, `1.5x`).
   - **16-Adımlı Canlı Ritim LED Matrisi**.
   - **8-Notalı İnteraktif Rove Synthboard (Piyano)**: `1-8` tuşlarıyla veya tıklamayla canlı çalınabilen notalar (C4 - C5).
   - **🎛️ 8-Pad Siber DJ Launchpad (Ses Tahtası)**:
     - `Q, W, E, R, A, S, D, F` klavye kısayolları ve dokunmatik neon pedlerle anında tetiklenen 8 prosedürel ses:
       - **Sub Kick** (`Q`), **Cyber Snare** (`W`), **Neon Hi-Hat** (`E`), **Laser Blaster** (`R`)
       - **Sub Wobble** (`A`), **Retro Coin** (`S`), **Warp Phase** (`D`), **Spark Pop** (`F`)
3. **🔍 Rove WASM Bayt, İkili (Binary) & Onaltılık (Hex) Müfettişi**:
   - Girilen metin veya sayıları canlı olarak Rove WASM doğrusal belleğinde işler.
   - Her karakter veya sayının 8-bit İkili (Binary), Onaltılık (Hex), ASCII kodunu ve dizi sağlama toplamını (checksum/GCD) gösterir.
4. **Reaktif Durum ve Sayaç Yöneticisi**:
   - `var counter: int` durumu Rove WebAssembly doğrusal belleğinde saklanır.
   - Artırma, azaltma, çarpma ve sıfırlama işlemleri saf WASM içinde gerçekleştirilir.
5. **WASM vs JavaScript Hız Karşılaştırması (Benchmark)**:
   - 25,000 ile 200,000 arasındaki sayılar için asal sayı tarama algoritması ($6k \pm 1$ optimizasyonu).
   - Rove WASM ile V8 JavaScript motorunun milisaniye cinsinden çalışma sürelerini görsel çubuklarla kıyaslar.
6. **Matematik Laboratuvarı**:
   - Hızlı Fibonacci, Collatz ($3n+1$) adım sayıcı, Öklid EBOB/GCD, `Array<int>` vektör toplamı ve UTF-8 string selamlama.

---

## 🛠️ Nasıl Derlenir? (Build)

Proje kök dizininden (`repo/`) şu komutu çalıştırarak `site.rove` dosyasını derleyebilirsiniz:

```bash
# Rove bundle komutu ile WebAssembly (.wasm, .wat, .mjs, .d.ts) çıktılarını üretin:
python src/cli.py bundle examples/web_site/site.rove -o examples/web_site/dist --package
```

Üretilen çıktılar (`examples/web_site/dist/`):
- `site.wasm`: Standalone `wasm32` ikili kod dosyası.
- `site.wat`: İnsan tarafından okunabilir WebAssembly metin formatı.
- `site.mjs`: ES2022 modül yükleyicisi ve `std/web` köprüsü.
- `site.d.ts`: TypeScript tip tanımlamaları.
- `package.json`: npm paket bildirimi.

---

## 🚀 Nasıl Çalıştırılır? (Run)

### Yöntem 1: Dahili Python Sunucusu (Önerilen)

```bash
python examples/web_site/server.py
```
Bu komut yerel bir HTTP sunucusu başlatır ve tarayıcınızda otomatik olarak `http://localhost:8080/index.html` adresini açar.

### Yöntem 2: Standart Python HTTP Sunucusu

```bash
cd examples/web_site
python -m http.server 8080
```
Ardından tarayıcınızda `http://localhost:8080` adresine gidin.

---

## 🧪 Otomatik Doğrulama Testi

WASM modülünün tüm fonksiyonlarını Node.js ortamında test etmek için:

```bash
node examples/web_site/verify.mjs
```

---

## 📂 Dosya Yapısı

```
examples/web_site/
├── site.rove          # Rove WebAssembly kaynak kodu (Grafik, mantık ve durum)
├── index.html        # Modern koyu tema, responsive web arayüzü
├── server.py         # Yerel test HTTP sunucusu
├── verify.mjs        # Node.js otomatik doğrulama testi
├── README.md         # Dokümantasyon
└── dist/             # Derlenmiş WebAssembly çıktıları
    ├── site.wasm     # WASM ikili dosyası
    ├── site.wat      # WebAssembly Text formatı
    ├── site.mjs      # ES modül yükleyicisi
    ├── site.d.ts     # TypeScript bildirimleri
    └── package.json  # Paket manifesti
```
