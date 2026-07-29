#!/usr/bin/env python3
"""
MarketPano - Excel uretici (yeni yapi)
======================================
Cikti: marketpano.xlsx

  Sheet 1-6  : Binance, OKX, Bybit, Bitget, Gate, Hyperliquid
               Her sheet o borsanin KENDI 24s perp hacminde ilk 150 varligi.
               Sutunlar: Tarih | Sira | Varlik | Fiyat | Market Cap | Perp Hacim | Open Interest
               Her gun 150 satir alta eklenir.

  Sheet 7    : Kontrat
               Satirlar CMC ilk 50. Her borsa 12 sutunluk blok halinde yan yana.
               Her guncellemede 50 satir alta eklenir.

  Sheet 8    : Notlar (kaynaklar, default funding, Hyperliquid formulu)

Girdiler (bu dosyanin klasorunde):
  arsiv/hacim/YYYY-MM-DD.json    (yoksa hacim*.json tek gun olarak alinir)
  arsiv/kontrat/YYYY-MM-DD.json  (yoksa kontrat*.json tek gun olarak alinir)
  arsiv/cmc/YYYY-MM-DD.json      (yoksa cmc.json)
  manuel-kaldirac.csv, manuel-funding.csv

Excel her calistirmada SIFIRDAN uretilir. Dosyaya elle yazilanlar korunmaz;
elle girilecek veriler manuel-*.csv dosyalarinda tutulur.
"""
import csv
import glob
import json
import os

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

os.chdir(os.path.dirname(os.path.abspath(__file__)))

OUT = "marketpano.xlsx"
BORSA_SIRASI = ["Binance", "OKX", "Bybit", "Bitget", "Gate", "Hyperliquid"]

HACIM_SUTUNLAR = ["Tarih", "Sira", "Varlik", "Fiyat ($)", "Market Cap ($)",
                  "Perp Hacim ($)", "Open Interest ($)"]

KONTRAT_SUTUNLAR = ["Index Price", "Min Miktar", "Min Tutar ($)", "Fiyat Adimi",
                    "Digit", "Miktar Adimi", "Max Kaldirac", "Funding %",
                    "Funding Periyot (saat)", "Derinlik +-1% ($)", "Spread %",
                    "Index Kirilimi"]

BORSA_RENK = {
    "Binance":     "F0B90B",
    "OKX":         "2B3139",
    "Bybit":       "FF7A00",
    "Bitget":      "7B61FF",
    "Gate":        "E5402B",
    "Hyperliquid": "50D2C2",
}
BORSA_DOLGU = {
    "Binance":     "FFFBF0",
    "OKX":         "F2F3F5",
    "Bybit":       "FFF6EE",
    "Bitget":      "F6F3FF",
    "Gate":        "FFF1EF",
    "Hyperliquid": "EFFBF9",
}

FONT = Font(name="Arial", size=10)
FONT_B = Font(name="Arial", size=10, bold=True)
HEAD_FONT = Font(name="Arial", size=10, bold=True, color="FFFFFF")
HEAD_FILL = PatternFill("solid", fgColor="003AFF")
THIN = Side(style="thin", color="D6DEEA")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


# ---------- yardimcilar ----------

def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def gunluk(klasor, tek_gun_dosyalari, anahtar):
    """arsiv/{klasor}/*.json -> {gun: icerik}. Arsiv yoksa eldeki dosyalari
    tek gun olarak birlestirip dondurur (ilk kurulumda ise yarar)."""
    gunler = {}
    for p in sorted(glob.glob(f"arsiv/{klasor}/*.json")):
        d = load_json(p)
        if d:
            gunler[os.path.basename(p)[:-5]] = d
    if gunler:
        return gunler
    birlesik, gun = {}, None
    for p in tek_gun_dosyalari:
        d = load_json(p)
        if not d:
            continue
        gun = gun or (d.get("generated_at") or "")[:10]
        if anahtar == "borsalar":
            birlesik.update(d.get("borsalar", {}))
        else:
            for a in d.get("assets", []):
                birlesik.setdefault(a["symbol"], {"symbol": a["symbol"],
                                                  "rank": a.get("rank"),
                                                  "exchanges": {}})
                birlesik[a["symbol"]]["exchanges"].update(a.get("exchanges") or {})
    if birlesik and gun:
        print(f"  ! arsiv/{klasor} bos -> eldeki dosyalar tek gun olarak alindi ({gun}).")
        if anahtar == "borsalar":
            return {gun: {"borsalar": birlesik}}
        return {gun: {"assets": sorted(birlesik.values(),
                                       key=lambda a: a.get("rank") or 9999)}}
    return {}


def cmc_gunluk():
    """{gun: {sembol: (fiyat, market_cap)}}"""
    gunler = {}
    yollar = sorted(glob.glob("arsiv/cmc/*.json"))
    arsivden = bool(yollar)
    if not yollar and os.path.exists("cmc.json"):
        yollar = ["cmc.json"]
    for p in yollar:
        d = load_json(p)
        if not d:
            continue
        gun = os.path.basename(p)[:-5] if arsivden else (d.get("generated_at") or "")[:10]
        gunler[gun] = {c["symbol"]: (c.get("price_usd"), c.get("market_cap_usd"))
                       for c in d.get("coins", [])}
    return gunler


def cmc_bak(cmc_gunleri, gun, sembol):
    """O gunun CMC verisinden fiyat+mcap. O gun yoksa en yakin onceki gune bakar."""
    if gun in cmc_gunleri:
        return cmc_gunleri[gun].get(sembol, (None, None))
    oncekiler = [g for g in sorted(cmc_gunleri) if g <= gun]
    if oncekiler:
        return cmc_gunleri[oncekiler[-1]].get(sembol, (None, None))
    if cmc_gunleri:
        return cmc_gunleri[sorted(cmc_gunleri)[0]].get(sembol, (None, None))
    return (None, None)


def load_manuel_kaldirac():
    out = {}
    try:
        with open("manuel-kaldirac.csv", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                v = (row.get("varlik") or "").strip().upper()
                k = (row.get("max_kaldirac") or "").strip()
                if v and k:
                    try:
                        out[v] = float(k)
                    except ValueError:
                        pass
    except FileNotFoundError:
        print("  ! manuel-kaldirac.csv yok -> Binance kaldirac bos kalacak.")
    return out


def kaldirac_csv_semboller():
    semboller = set()
    try:
        with open("manuel-kaldirac.csv", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                v = (row.get("varlik") or "").strip().upper()
                if v:
                    semboller.add(v)
    except FileNotFoundError:
        pass
    return semboller


def kaldirac_csv_tamamla(semboller):
    """Kontrat listesinde olup CSV'de olmayan varliklari BOS satir olarak ekler.
    Mevcut satirlara ve girilmis degerlere DOKUNMAZ."""
    mevcut = kaldirac_csv_semboller()
    eksik = [s for s in semboller if s not in mevcut]
    if not eksik:
        return
    yeni = not os.path.exists("manuel-kaldirac.csv")
    with open("manuel-kaldirac.csv", "a", encoding="utf-8") as f:
        if yeni:
            f.write("varlik,max_kaldirac\n")
        for s in eksik:
            f.write(f"{s},\n")
    print(f"  manuel-kaldirac.csv'ye {len(eksik)} yeni varlik eklendi (bos): "
          f"{', '.join(eksik[:8])}{' ...' if len(eksik) > 8 else ''}")


def load_manuel_funding():
    out = {}
    try:
        with open("manuel-funding.csv", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                b = (row.get("borsa") or "").strip()
                d = (row.get("default_funding") or "").strip()
                if b and d:
                    try:
                        out[b] = float(d)
                    except ValueError:
                        pass
    except FileNotFoundError:
        print("  ! manuel-funding.csv yok.")
    return out


def breakdown_text(bd):
    """Index kirilimini tek hucreye sigacak metne cevirir."""
    if not bd:
        return ""
    parts = []
    for c in bd:
        if isinstance(c, dict):
            ex, w = c.get("exchange"), c.get("weight")
        else:
            ex = c[0]
            w = c[1] if len(c) > 1 else None
        if not ex:
            continue
        if w is None:
            parts.append(str(ex))
        else:
            wp = w * 100 if w <= 1 else w
            parts.append(f"{ex}:{wp:.0f}%")
    return ", ".join(parts)


# ---------- sheet'ler ----------

def sheet_hacim(wb, borsa, gunler, cmc_gunleri, ilk=False):
    ws = wb.active if ilk else wb.create_sheet()
    ws.title = borsa
    ws.sheet_properties.tabColor = BORSA_RENK.get(borsa, "003AFF")
    for c, h in enumerate(HACIM_SUTUNLAR, 1):
        cell = ws.cell(1, c, h)
        cell.fill = HEAD_FILL
        cell.font = HEAD_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER
    ws.freeze_panes = "A2"
    dolgu = PatternFill("solid", fgColor=BORSA_DOLGU.get(borsa, "FFFFFF"))
    r = 2
    for gun in sorted(gunler):
        satirlar = (gunler[gun].get("borsalar") or {}).get(borsa) or []
        for s in satirlar:
            fiyat, mcap = cmc_bak(cmc_gunleri, gun, s.get("symbol"))
            vals = [gun, s.get("sira"), s.get("symbol"), fiyat, mcap,
                    s.get("perp_volume_usd"), s.get("open_interest_usd")]
            for i, v in enumerate(vals, 1):
                cell = ws.cell(r, i, v)
                cell.font = FONT_B if i == 3 else FONT
                cell.border = BORDER
                cell.fill = dolgu
            ws.cell(r, 4).number_format = '#,##0.########'
            for col in (5, 6, 7):
                ws.cell(r, col).number_format = '#,##0'
            r += 1
    for col, w in zip("ABCDEFG", [11, 6, 12, 15, 20, 20, 20]):
        ws.column_dimensions[col].width = w
    if r > 2:
        ws.auto_filter.ref = f"A1:G{r - 1}"
    return r - 2


def sheet_kontrat(wb, gunler, manuel_kaldirac):
    ws = wb.create_sheet(title="Kontrat")
    ws.sheet_properties.tabColor = "003AFF"
    n = len(KONTRAT_SUTUNLAR)

    for c, h in enumerate(["Tarih", "Varlik"], 1):
        ws.merge_cells(start_row=1, start_column=c, end_row=2, end_column=c)
        cell = ws.cell(1, c, h)
        cell.fill = HEAD_FILL
        cell.font = HEAD_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDER
    for bi, borsa in enumerate(BORSA_SIRASI):
        c0 = 3 + bi * n
        ws.merge_cells(start_row=1, start_column=c0, end_row=1, end_column=c0 + n - 1)
        cell = ws.cell(1, c0, borsa)
        cell.fill = PatternFill("solid", fgColor=BORSA_RENK.get(borsa, "003AFF"))
        koyu = borsa in ("Binance", "Hyperliquid")
        cell.font = Font(name="Arial", size=11, bold=True,
                         color="3A2F00" if koyu else "FFFFFF")
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDER
        for j, h in enumerate(KONTRAT_SUTUNLAR):
            hc = ws.cell(2, c0 + j, h)
            hc.fill = PatternFill("solid", fgColor="EEF3FB")
            hc.font = Font(name="Arial", size=9, bold=True, color="35496B")
            hc.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            hc.border = BORDER
    ws.freeze_panes = "C3"

    r = 3
    for gun in sorted(gunler):
        assets = gunler[gun].get("assets") or []
        for a in sorted(assets, key=lambda x: x.get("rank") or 9999):
            sym = a["symbol"]
            c1 = ws.cell(r, 1, gun); c1.font = FONT; c1.border = BORDER
            c2 = ws.cell(r, 2, sym); c2.font = FONT_B; c2.border = BORDER
            for bi, borsa in enumerate(BORSA_SIRASI):
                c0 = 3 + bi * n
                k = (a.get("exchanges") or {}).get(borsa) or {}
                kaldirac = k.get("max_leverage")
                if kaldirac is None and borsa == "Binance":
                    kaldirac = manuel_kaldirac.get(sym)
                fund = k.get("funding")
                spr = k.get("spread_pct")   # collect.py bunu ZATEN yuzde olarak verir
                vals = [
                    k.get("index_price"),
                    k.get("min_qty"),
                    k.get("min_notional"),
                    k.get("tick_size"),
                    k.get("digit"),
                    k.get("step_size"),
                    kaldirac,
                    (fund * 100) if fund is not None else None,   # funding ham oran -> yuzde
                    k.get("funding_interval_h"),
                    k.get("depth_1pct_usd"),
                    spr,
                    breakdown_text(k.get("index_breakdown")),
                ]
                dolgu = PatternFill("solid", fgColor=BORSA_DOLGU.get(borsa, "FFFFFF"))
                for j, v in enumerate(vals):
                    cell = ws.cell(r, c0 + j, v)
                    cell.font = FONT
                    cell.border = BORDER
                    cell.fill = dolgu
                ws.cell(r, c0 + 0).number_format = '#,##0.########'
                for off in (1, 3, 5):
                    ws.cell(r, c0 + off).number_format = '0.########'
                ws.cell(r, c0 + 2).number_format = '#,##0.##'
                ws.cell(r, c0 + 4).number_format = '0'
                ws.cell(r, c0 + 6).number_format = '0"x"'
                ws.cell(r, c0 + 7).number_format = '0.0000"%"'
                ws.cell(r, c0 + 8).number_format = '0.0'
                ws.cell(r, c0 + 9).number_format = '#,##0'
                ws.cell(r, c0 + 10).number_format = '0.0000"%"'
            r += 1

    ws.column_dimensions["A"].width = 11
    ws.column_dimensions["B"].width = 11
    genislik = [13, 11, 11, 11, 6, 11, 9, 10, 9, 15, 9, 34]
    for bi in range(len(BORSA_SIRASI)):
        for j, w in enumerate(genislik):
            ws.column_dimensions[get_column_letter(3 + bi * n + j)].width = w
    if r > 3:
        ws.auto_filter.ref = f"A2:{get_column_letter(2 + len(BORSA_SIRASI) * n)}{r - 1}"
    return r - 3


def sheet_notlar(wb, hacim_gun, kontrat_gun, manuel_kaldirac, manuel_funding):
    ws = wb.create_sheet(title="Notlar")
    ws.cell(1, 1, "MarketPano - notlar ve kaynaklar").font = Font(name="Arial", size=12, bold=True)
    satirlar = [
        ("Yapı", ""),
        ("Borsa sheet'leri (6 adet)",
         "O borsanın KENDİ 24 saatlik perp hacmine göre ilk 150 varlığı. Her gün 150 satır alta eklenir."),
        ("Sıra sütunu", "O borsa içindeki hacim sırası (1-150). Borsalar arasında farklı olabilir."),
        ("Fiyat ve Market Cap", "CMC ilk 150'den gelir. O listede olmayan varlıklarda boş kalır."),
        ("Kontrat sheet'i",
         "Satırlar CMC market cap ilk 50. Her borsa 12 sütunluk blok halinde yan yana. Her güncellemede 50 satır alta eklenir."),
        ("Arşivdeki gün sayısı", f"hacim: {hacim_gun} gün · kontrat: {kontrat_gun} gün"),
        ("", ""),
        ("Veri kaynakları", ""),
        ("Index, min miktar/tutar, adımlar, digit, funding, periyot, kaldıraç",
         "İlgili borsanın public API'si"),
        ("Derinlik +-1% ve Spread", "Order book'tan hesaplanır (ham dolar değeri, etiket yok)"),
        ("Boş blok / boş hücre", "O borsada perp listeli değil ya da o gün veri çekilemedi"),
        ("Index kırılımı - Binance, OKX, Gate", "API'den (kaynak borsa + ağırlık)"),
        ("Index kırılımı - Bitget", "Net public endpoint bulunamadı, boş kalabilir"),
        ("Index kırılımı - Bybit", "Bybit yayınlamıyor (dinamik hesaplıyor), boş"),
        ("Index kırılımı - Hyperliquid", "Sabit formül, aşağıda"),
        ("", ""),
        ("Hyperliquid index formülü (dokümanlı, sabit)", ""),
        ("Yöntem", "AĞIRLIKLI MEDYAN (ağırlıklı ortalama DEĞİL) - ağırlıklar medyan oyudur"),
        ("Normal varlıklar (ana likidite dışarıda, örn. BTC)",
         "Binance 3 (%27,3) · OKX 2 (%18,2) · Bybit 2 (%18,2) · Kraken 1 (%9,1) · "
         "Kucoin 1 (%9,1) · Gate 1 (%9,1) · MEXC 1 (%9,1) — Hyperliquid hariç"),
        ("Ana likiditesi Hyperliquid'de olanlar (örn. HYPE)",
         "Sadece Hyperliquid; dış kaynaklar yeterli likiditeye kadar dahil edilmez"),
        ("", ""),
        ("Default funding (faiz bileşeni, borsa başına sabit)", ""),
    ]
    for b in BORSA_SIRASI:
        d = manuel_funding.get(b)
        satirlar.append(("   " + b, f"%{d} / 8 saat" if d is not None else "teyit bekliyor / girilmedi"))
    satirlar += [
        ("", ""),
        ("Elle girilen veriler", ""),
        ("manuel-kaldirac.csv",
         f"Binance max kaldıraç (API'de yok) - {len(manuel_kaldirac)} varlık dolu"),
        ("manuel-funding.csv", "Default funding değerleri (borsa başına)"),
        ("Önemli", "Elle girilen değerler tarih bazlı değildir; tüm günlerde aynı görünür"),
        ("", ""),
        ("Excel nasıl üretilir", ""),
        ("Yöntem", "Her çalıştırmada arşivden sıfırdan üretilir; dosyaya elle yazılanlar korunmaz"),
        ("Elle veri girmek için", "manuel-*.csv dosyalarını GitHub'da düzenle"),
    ]
    r = 3
    for a, b in satirlar:
        ca, cb = ws.cell(r, 1, a), ws.cell(r, 2, b)
        ca.font = FONT_B if (a and not b) else FONT
        cb.font = FONT
        cb.alignment = Alignment(wrap_text=True, vertical="top")
        r += 1
    ws.column_dimensions["A"].width = 56
    ws.column_dimensions["B"].width = 92
    return ws


def main():
    hacim_gunler = gunluk("hacim", ["hacim_github.json", "hacim_local.json", "hacim.json"], "borsalar")
    kontrat_gunler = gunluk("kontrat", ["kontrat_github.json", "kontrat_local.json", "kontrat.json"], "assets")
    cmc_gunleri = cmc_gunluk()
    manuel_kaldirac = load_manuel_kaldirac()
    manuel_funding = load_manuel_funding()

    if not hacim_gunler and not kontrat_gunler:
        print("! Ne hacim ne kontrat verisi bulundu. Once veri cekilmeli.")
        return 1

    kontrat_semboller = []
    for gun in sorted(kontrat_gunler):
        for a in kontrat_gunler[gun].get("assets", []):
            if a["symbol"] not in kontrat_semboller:
                kontrat_semboller.append(a["symbol"])
    if kontrat_semboller:
        kaldirac_csv_tamamla(kontrat_semboller)
        manuel_kaldirac = load_manuel_kaldirac()

    wb = openpyxl.Workbook()
    ozet = []
    for i, borsa in enumerate(BORSA_SIRASI):
        adet = sheet_hacim(wb, borsa, hacim_gunler, cmc_gunleri, ilk=(i == 0))
        ozet.append(f"{borsa}:{adet}")
    kontrat_satir = sheet_kontrat(wb, kontrat_gunler, manuel_kaldirac)
    sheet_notlar(wb, len(hacim_gunler), len(kontrat_gunler), manuel_kaldirac, manuel_funding)

    wb.save(OUT)
    print(f"[EXCEL] {OUT} yazildi.")
    print(f"  Sheet'ler    : {', '.join(wb.sheetnames)}")
    print(f"  Hacim satir  : {' | '.join(ozet)}")
    print(f"  Kontrat satir: {kontrat_satir}")
    print(f"  Arsiv gunu   : hacim {len(hacim_gunler)} | kontrat {len(kontrat_gunler)} | cmc {len(cmc_gunleri)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
