# Perp Listeleme Araştırması — Sıfırdan Kurulum Kılavuzu

Daha önce hiç API kullanmadıysan, Python bilmiyorsan: doğru yerdesin.
Bu kılavuz seni hiçbir şey atlamadan sonuca götürür. **Kod yazmayacaksın, sadece kopyala-yapıştır yapacaksın.**

---

## Önce şunu anla (2 dakika)

**"API ile veri çekmek" korkutucu değil.** Bu borsaların fiyat/hacim verisi herkese açık.
Hesap açmana, para ödemene, "API key" almana **gerek yok**. `collect.py` adlı dosya
senin yerine 8 borsaya gidip veriyi alıyor. Senin tek yapacağın onu çalıştırmak.

Elinde 4 dosya var:

| Dosya | Ne işe yarar |
|-------|--------------|
| `collect.py` | Veriyi çeken script. Çalışınca `data.json` üretir. |
| `dashboard.html` | Veriyi filtreleyip grafikle gösteren ekran. |
| `data.json` | Çekilen veri buraya yazılır (script üretir). |
| `.github/workflows/collect.yml` | GitHub'ın her gün otomatik çekmesini sağlar. |

İki kurulum yolu var. **A yolu** en kolayı ve sana en uygunu (bilgisayara hiç dokunmadan).
**B yolu** istersen bir kez kendi bilgisayarında denemek için.

---

## A YOLU — GitHub'da otomatik (önerilen, Python bilmene gerek yok)

GitHub senin için her gün bulutta çalıştırır, bilgisayarın kapalı olsa bile.

### 1. GitHub hesabı aç
github.com → ücretsiz kayıt ol (zaten varsa atla).

### 2. Yeni repo (depo) oluştur
- Sağ üstte **+** → **New repository**
- İsim ver (örn. `perp-research`)
- **Public** seç (Actions ücretsiz çalışsın diye)
- **Create repository**

### 3. Dosyaları yükle
- Açılan sayfada **uploading an existing file** linkine tıkla
- `collect.py`, `dashboard.html`, `data.json` dosyalarını sürükle-bırak
- **Commit changes**

> `.github/workflows/collect.yml` dosyasını yüklemek için: repoda
> **Add file → Create new file** de, isim kutusuna tam olarak
> `.github/workflows/collect.yml` yaz (eğik çizgiler klasörü otomatik oluşturur),
> içine `collect.yml` dosyasının içeriğini yapıştır, **Commit**.

### 4. Actions'a izin ver
- Repoda üstteki **Settings → Actions → General**
- **Workflow permissions** bölümünde **Read and write permissions** seç → **Save**
- (Bu, script'in güncel `data.json`'u repoya geri yazabilmesi için gerekli.)

### 5. İlk çalıştırmayı elle tetikle
- Üstteki **Actions** sekmesi → soldan **Veri Topla** → sağda **Run workflow** → **Run workflow**
- 1-2 dakika bekle, yeşil tik gelince `data.json` güncellenmiş olur.
- Bundan sonra **her gün otomatik** çalışır, hiçbir şey yapmana gerek yok.

### 6. Dashboard'u görmek için (ücretsiz, GitHub Pages)
- **Settings → Pages**
- **Source** olarak **Deploy from a branch** → **main** / **root** → **Save**
- 1 dakika sonra sana bir adres verir:
  `https://KULLANICIADIN.github.io/perp-research/dashboard.html`
- Bu adresi açınca dashboard'u canlı görürsün. Her veri güncellemesinde otomatik tazelenir.

**Bitti.** Artık her sabah taze veriyle dolu bir dashboard'un var.

---

## B YOLU — Kendi bilgisayarında bir kez denemek

Sadece "önce elimde görsem" diyorsan. Zorunlu değil.

### 1. Python kurulu mu bak
- Windows: Başlat → `cmd` yaz → aç → `python --version` yaz, Enter.
- Mac: Spotlight → `Terminal` → `python3 --version` yaz, Enter.
- Bir sürüm numarası (örn. 3.11) görüyorsan kuruludur. Yoksa python.org'dan indir.

### 2. Gerekli paketi yükle
Aynı pencerede yaz:
```
pip install requests
```
(Mac'te çalışmazsa `pip3 install requests` dene.)

### 3. Klasöre git ve scripti çalıştır
Dosyaların olduğu klasöre geçip:
```
python collect.py
```
(Mac: `python3 collect.py`)

Ekranda borsa borsa "çekiliyor..." yazılarını görürsün. Bitince klasörde
`data.json` oluşur. Bu birkaç dakika sürebilir (Coinbase ve Binance OI yavaştır).

### 4. Dashboard'u aç
Dosyayı **çift tıklayıp açma** — tarayıcı güvenliği `data.json` okumayı engeller.
Bunun yerine aynı klasörde küçük bir yerel sunucu başlat:
```
python -m http.server
```
(Mac: `python3 -m http.server`)

Sonra tarayıcıda şunu aç:
```
http://localhost:8000/dashboard.html
```
Veri ve grafikler gelir. Kapatmak için pencerede Ctrl+C.

---

## Dashboard'da ne yapabilirsin

- **Sırala**: perp hacme, open interest'e, market cap'e göre.
- **Min. Perp Borsa Sayısı**: "en az kaç borsada perp'i var" filtresi — listeleme kararının kalbi.
- **Min. Open Interest**: belirli bir eşiğin altındaki coinleri ele.
- **Ara**: sembol/isim ile.
- **Tablo başlıklarına tıkla**: o sütuna göre sıralar.
- Üstteki iki grafik filtrelenmiş ilk 12 asset'i gösterir (perp hacmi borsa kırılımlı + toplam OI).

---

## Sık sorulanlar

**"Coinbase kolonları neden boş?"**
Coinbase'te USDT paritesi ve perp ürünü çok sınırlı. Bu beklenen, hata değil.

**"Bir borsa hata verdi, çekemedi."**
Sorun değil — script o borsayı atlar, diğerleriyle devam eder. Bir borsanın API'si
o an yavaşsa ertesi gün düzelir.

**"Çekilen sayılar tam doğru mu?"**
Open interest'i bazı borsalar adet cinsinden verir; script fiyatla çarpıp USD'ye
çevirir, bu küçük yuvarlama farkları olabilir. Karşılaştırma/sıralama için yeterince
sağlıklı; kuruşu kuruşuna muhasebe için değil.

**"Daha fazla asset istiyorum."**
`collect.py` içinde en üstteki `TOP_N_ASSETS = 50` satırını değiştir (örn. 100 yap).

**"Saati değiştirmek istiyorum."**
`.github/workflows/collect.yml` içindeki `cron: '0 6 * * *'` satırı. 06:00 UTC = ~09:00 TR.
Yeni saat üretmek için crontab.guru sitesini kullan.
