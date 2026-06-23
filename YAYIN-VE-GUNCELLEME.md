# MarketPano — Yayına Alma ve Güncelleme Kılavuzu

Bu dosya iki şeyi anlatır:
1. Dashboard'u canlı bir linke nasıl çevirirsin (GitHub Pages).
2. İleride tasarımı değiştirmek istediğinde ne yaparsın.

---

## BÖLÜM 1 — Canlı link (GitHub Pages)

Dosyaların zaten GitHub'da. Şimdi dashboard'u herkesin (ya da sadece senin)
açabileceği bir web adresine çeviriyoruz. Bilgisayara hiçbir şey kurmana gerek yok.

### Adımlar
1. GitHub'da repona gir (marketpano).
2. Üstten **Settings** → soldan **Pages**.
3. **Source** bölümünde **Deploy from a branch** seç.
4. **Branch**: `main`, klasör: `/ (root)` → **Save**.
5. ~1 dakika bekle. Sayfa yenilenince yukarıda yeşil bir kutuda adresin çıkar:
   ```
   https://KULLANICIADIN.github.io/marketpano/dashboard.html
   ```
   (Senin için: `https://batuhanhelvaci-hub.github.io/marketpano/dashboard.html`)
6. Bu adresi aç → dashboard canlı, gerçek veriyle. Bu linki kaydet/paylaş.

### Günlük güncelleme — senin yapman gereken: HİÇBİR ŞEY
- GitHub Actions her gün **Türkiye saati 12:00'da** (UTC 09:00) otomatik çalışır.
- O an 8 borsadan + CoinGecko'dan taze veri çeker, `data.json`'u yeniler.
- Dashboard'daki üstteki tarih damgası da otomatik o güne/saate güncellenir.
- Bilgisayarın kapalı olsa bile çalışır.
- İstersen **Actions → Veri Topla → Run workflow** ile elle de tetikleyebilirsin.

### Saati değiştirmek istersen
`.github/workflows/collect.yml` içindeki şu satır:
```
- cron: '0 9 * * *'
```
`0 9` = UTC 09:00 = Türkiye 12:00. Türkiye saati = UTC + 3.
Örnek: Türkiye 15:00 istiyorsan → UTC 12:00 → `0 12 * * *`.
Yeni saat üretmek için: https://crontab.guru

---

## BÖLÜM 2 — Dashboard tasarımını sonradan değiştirmek

Dashboard'un tüm görünümü tek dosyada: **dashboard.html**.
İleride renk, sütun, başlık vs. değiştirmek istersen iki yol var.

### Yol A — Claude'a yaptır (en kolay)
1. GitHub'dan `dashboard.html` dosyasını indir
   (repoda dosyaya tıkla → sağ üstte **Download raw file**).
2. Claude'a bu dosyayı yükle ve ne istediğini yaz
   (örn. "şu sütunu kaldır", "şu rengi değiştir", "şunu ekle").
3. Claude güncellenmiş `dashboard.html`'i geri verir.
4. GitHub'da eski `dashboard.html`'in üstüne yükle:
   repoda dosyaya tıkla → kalem (Edit) ikonu → içeriği değiştir, ya da
   **Add file → Upload files** ile aynı isimde yükle → **Commit changes**.
5. ~1 dakika sonra canlı link otomatik güncellenir.

### Yol B — Kendin düzenle
`dashboard.html` tek dosya; en üstteki `<style>` bölümünde renkler,
`EXCH_COLORS` kısmında borsa renkleri duruyor. Düzenleyip aynı şekilde
GitHub'a geri yükle.

### Önemli not
Veriyi çeken kısım (`collect.py`) ile görünümü çizen kısım (`dashboard.html`)
ayrıdır. Tasarım değişikliği için sadece `dashboard.html` ile uğraşırsın;
`collect.py`'ye dokunman gerekmez. Veri akışı kendi başına devam eder.

---

## Dosyalar ne işe yarıyor (hatırlatma)

| Dosya | Görevi |
|-------|--------|
| `collect.py` | 8 borsa + CoinGecko'dan veri çeker, `data.json` üretir |
| `dashboard.html` | Veriyi gösteren ekran (tasarım burada) |
| `data.json` | Çekilen güncel veri (her gün otomatik yenilenir) |
| `.github/workflows/collect.yml` | Her gün 12:00'da (TR) otomatik çalıştırır |

## Sık karşılaşılanlar
- **Coinbase kolonları boş** → normal, Coinbase'te USDT perp yok.
- **Perp USDC sütunu boş** → şu an perp hacmi USDT olarak çekiliyor, beklenen.
- **Bir borsa o gün veri vermediyse** → script onu atlar, diğerleriyle devam eder.
- **Pages linki açılmıyor** → Settings → Pages'te branch'in `main` ve `/root` olduğundan emin ol; ilk kurulumda 1-2 dakika gecikebilir.
