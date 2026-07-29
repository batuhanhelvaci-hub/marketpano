#!/usr/bin/env python3
"""
MarketPano - Excel uretici
===========================
Girdiler (bu dosyanin bulundugu klasorde):
  cmc.json                    -> Sheet 1 (CMC ilk 150)
  arsiv/kontrat/YYYY-MM-DD.json -> gun gun kontrat verisi (6 borsa)
  arsiv/borsa/YYYY-MM-DD.json   -> gun gun perp hacim + open interest
  manuel-kaldirac.csv         -> Binance max kaldirac (elle)
  manuel-funding.csv          -> default funding (elle)

Cikti:
  marketpano.xlsx
    Sheet 1        : CMC 150
    Sheet 2..51    : her varlik icin ayri sheet (CMC market cap ilk 50)
                     Satirlar: her gun icin 6 borsa (6'li bloklar)
    Son sheet      : Notlar (kaynak ve varsayimlar)

Excel her calistirmada SIFIRDAN uretilir (arsivden). Boylece cift kayit olmaz,
gecmis bir hata duzeltilirse tum gunler duzelir.
"""
import json
import csv
import glob
import os

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

os.chdir(os.path.dirname(os.path.abspath(__file__)))

TOP_N = 50
OUT = "marketpano.xlsx"

# Satir sirasi (kullanicinin istedigi sira)
BORSA_SIRASI = ["Binance", "OKX", "Bybit", "Bitget", "Gate", "Hyperliquid"]

# Varlik sheet'lerinin sutunlari
SUTUNLAR = [
    "Tarih", "Borsa", "Listeli", "Index Price", "Index Kirilimi",
    "Min Miktar", "Min Tutar ($)", "Fiyat Adimi", "Digit", "Miktar Adimi",
    "Max Kaldirac", "Funding %", "Funding Periyot (saat)", "Default Funding %",
    "Funding Tavan %", "Derinlik +-1% ($)", "Spread %",
    "Perp Hacim 24s ($)", "Open Interest ($)",
]

BORSA_DOLGU = {
    "Binance":     PatternFill("solid", fgColor="FFF7E0"),
    "OKX":         PatternFill("solid", fgColor="ECEDEF"),
    "Bybit":       PatternFill("solid", fgColor="FFEEDD"),
    "Bitget":      PatternFill("solid", fgColor="EFE9FF"),
    "Gate":        PatternFill("solid", fgColor="FFE6E2"),
    "Hyperliquid": PatternFill("solid", fgColor="E0F7F3"),
}

FONT = Font(name="Arial", size=10)
FONT_B = Font(name="Arial", size=10, bold=True)
HEAD_FONT = Font(name="Arial", size=10, bold=True, color="FFFFFF")
HEAD_FILL = PatternFill("solid", fgColor="003AFF")
THIN = Side(style="thin", color="D6DEEA")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def load_manuel_kaldirac():
    """manuel-kaldirac.csv -> {VARLIK: kaldirac}. Yoksa bos doner."""
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


def load_manuel_funding():
    """manuel-funding.csv -> {Borsa: default_funding_yuzde}. Bos hucreler atlanir."""
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
        print("  ! manuel-funding.csv yok -> default funding bos kalacak.")
    return out


def kaldirac_csv_semboller():
    """manuel-kaldirac.csv'de bulunan TUM semboller (degeri bos olanlar dahil)."""
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


def kaldirac_csv_tamamla(ilk50):
    """CMC ilk 50'de olup manuel-kaldirac.csv'de olmayan varliklari BOS satir olarak ekler.
    Mevcut satirlara ve girilmis degerlere DOKUNMAZ. Boylece liste degistikce
    yeni varlik kendiliginden gorunur, sen sadece sayiyi yazarsin."""
    mevcut = kaldirac_csv_semboller()
    eksik = [s for s in ilk50 if s not in mevcut]
    if not eksik:
        return []
    yeni_dosya = not os.path.exists("manuel-kaldirac.csv")
    with open("manuel-kaldirac.csv", "a", encoding="utf-8") as f:
        if yeni_dosya:
            f.write("varlik,max_kaldirac\n")
        for s in eksik:
            f.write(f"{s},\n")
    print(f"  manuel-kaldirac.csv'ye {len(eksik)} yeni varlik eklendi (bos): {', '.join(eksik[:8])}"
          f"{' ...' if len(eksik) > 8 else ''}")
    return eksik


def breakdown_text(bd):
    """Index kirilimini tek hucreye sigacak metne cevirir."""
    if not bd:
        return ""
    parts = []
    for c in bd:
        if isinstance(c, dict):
            ex, w = c.get("exchange"), c.get("weight")
        else:
            ex, w = (c[0], c[1]) if len(c) > 1 else (c[0], None)
        if not ex:
            continue
        if w is None:
            parts.append(str(ex))
        else:
            wp = w * 100 if w <= 1 else w
            parts.append(f"{ex}:{wp:.0f}%")
    return ", ".join(parts)


def gunluk_kontrat_verisi():
    """arsiv/kontrat/*.json -> {gun: {sym: {borsa: row}}}
    Arsiv yoksa mevcut kontrat*.json dosyalarini tek gun olarak kullanir."""
    gunler = {}
    dosyalar = sorted(glob.glob("arsiv/kontrat/*.json"))
    for p in dosyalar:
        gun = os.path.basename(p)[:-5]
        d = load_json(p)
        if not d:
            continue
        gunler[gun] = {a["symbol"]: (a.get("exchanges") or {}) for a in d.get("assets", [])}
    if not gunler:
        # Arsiv henuz yok: elde ne varsa tek gun olarak al
        birlesik = {}
        gun = None
        for p in ("kontrat_github.json", "kontrat_local.json", "kontrat.json"):
            d = load_json(p)
            if not d:
                continue
            gun = gun or (d.get("generated_at") or "")[:10]
            for a in d.get("assets", []):
                birlesik.setdefault(a["symbol"], {}).update(a.get("exchanges") or {})
        if birlesik and gun:
            gunler[gun] = birlesik
            print(f"  ! arsiv/kontrat bos -> mevcut kontrat dosyalari tek gun olarak alindi ({gun}).")
    return gunler


def gunluk_hacim_verisi():
    """arsiv/borsa/*.json -> {gun: {sym: {borsa: {vol, oi}}}}"""
    gunler = {}
    for p in sorted(glob.glob("arsiv/borsa/*.json")):
        gun = os.path.basename(p)[:-5]
        d = load_json(p)
        if not d:
            continue
        gunler[gun] = {a["symbol"]: (a.get("exchanges") or {}) for a in d.get("assets", [])}
    if not gunler:
        birlesik = {}
        gun = None
        for p in ("borsa_github.json", "borsa_local.json"):
            d = load_json(p)
            if not d:
                continue
            gun = gun or (d.get("generated_at") or "")[:10]
            for a in d.get("assets", []):
                birlesik.setdefault(a["symbol"], {}).update(a.get("exchanges") or {})
        if birlesik and gun:
            gunler[gun] = birlesik
    return gunler


def stil_baslik(ws, basliklar):
    for c, h in enumerate(basliklar, 1):
        cell = ws.cell(1, c, h)
        cell.fill = HEAD_FILL
        cell.font = HEAD_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER
    ws.freeze_panes = "A2"


def sheet_cmc(wb, cmc):
    ws = wb.active
    ws.title = "CMC 150"
    basliklar = ["Sira", "Varlik", "Isim", "Fiyat ($)", "Market Cap ($)",
                 "Spot Hacim 24s ($)", "7 Gun %"]
    stil_baslik(ws, basliklar)
    coins = sorted((cmc or {}).get("coins", []), key=lambda c: c.get("rank") or 9999)
    for r, c in enumerate(coins, 2):
        vals = [c.get("rank"), c.get("symbol"), c.get("name"), c.get("price_usd"),
                c.get("market_cap_usd"), c.get("spot_volume_24h_usd"),
                c.get("percent_change_7d")]
        for i, v in enumerate(vals, 1):
            cell = ws.cell(r, i, v)
            cell.font = FONT
            cell.border = BORDER
        ws.cell(r, 4).number_format = '#,##0.########'
        ws.cell(r, 5).number_format = '#,##0'
        ws.cell(r, 6).number_format = '#,##0'
        ws.cell(r, 7).number_format = '0.00"%"'
        # ilk 50 (kendi sheet'i olanlar) kalin
        if (c.get("rank") or 9999) <= TOP_N:
            ws.cell(r, 2).font = FONT_B
    for col, w in zip("ABCDEFG", [7, 10, 22, 16, 20, 20, 10]):
        ws.column_dimensions[col].width = w
    ws.auto_filter.ref = f"A1:G{len(coins) + 1}"
    return ws


def sheet_varlik(wb, sym, gunler_kontrat, gunler_hacim, manuel_kaldirac, manuel_funding):
    ws = wb.create_sheet(title=sym[:31])
    stil_baslik(ws, SUTUNLAR)
    r = 2
    for gun in sorted(gunler_kontrat.keys()):
        kontrat_gun = gunler_kontrat.get(gun, {}).get(sym, {})
        hacim_gun = gunler_hacim.get(gun, {}).get(sym, {})
        for borsa in BORSA_SIRASI:
            k = kontrat_gun.get(borsa) or {}
            h = hacim_gun.get(borsa) or {}
            listeli = "Var" if k else ("Var" if h else "Yok")

            kaldirac = k.get("max_leverage")
            if kaldirac is None and borsa == "Binance":
                kaldirac = manuel_kaldirac.get(sym)

            fund = k.get("funding")
            spr = k.get("spread_pct")
            cap = k.get("funding_cap")

            vals = [
                gun,
                borsa,
                listeli,
                k.get("index_price"),
                breakdown_text(k.get("index_breakdown")),
                k.get("min_qty"),
                k.get("min_notional"),
                k.get("tick_size"),
                k.get("digit"),
                k.get("step_size"),
                kaldirac,
                (fund * 100) if fund is not None else None,
                k.get("funding_interval_h"),
                manuel_funding.get(borsa),
                (cap * 100) if cap is not None else None,
                k.get("depth_1pct_usd"),
                (spr * 100) if spr is not None else None,
                h.get("perp_volume_usd"),
                h.get("open_interest_usd"),
            ]
            for i, v in enumerate(vals, 1):
                cell = ws.cell(r, i, v)
                cell.font = FONT
                cell.border = BORDER
                cell.fill = BORSA_DOLGU.get(borsa, PatternFill())
            ws.cell(r, 2).font = FONT_B
            ws.cell(r, 4).number_format = '#,##0.########'
            for col in (6, 8, 10):
                ws.cell(r, col).number_format = '0.########'
            ws.cell(r, 7).number_format = '#,##0.##'
            ws.cell(r, 9).number_format = '0'
            ws.cell(r, 11).number_format = '0"x"'
            ws.cell(r, 12).number_format = '0.0000"%"'
            ws.cell(r, 13).number_format = '0.0'
            ws.cell(r, 14).number_format = '0.0000"%"'
            ws.cell(r, 15).number_format = '0.0000"%"'
            ws.cell(r, 16).number_format = '#,##0'
            ws.cell(r, 17).number_format = '0.0000"%"'
            ws.cell(r, 18).number_format = '#,##0'
            ws.cell(r, 19).number_format = '#,##0'
            r += 1
    genislikler = [11, 12, 8, 14, 40, 12, 12, 12, 7, 12, 11, 11, 11, 11, 11, 16, 10, 18, 18]
    for c, w in enumerate(genislikler, 1):
        ws.column_dimensions[get_column_letter(c)].width = w
    if r > 2:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(SUTUNLAR))}{r - 1}"
    return ws


def sheet_notlar(wb, gun_sayisi, manuel_kaldirac, manuel_funding):
    ws = wb.create_sheet(title="Notlar")
    satirlar = [
        ("MarketPano - kontrat verileri", ""),
        ("", ""),
        ("Yapı", ""),
        ("Sheet 1", "CMC market cap ilk 150 (referans liste)"),
        ("Sheet 2 ve sonrası", f"CMC ilk {TOP_N} varlık, her biri ayrı sheet"),
        ("Varlık sheet'i satırları", "Her gün için 6 borsa (6'lı bloklar), tarihe göre artan"),
        ("Arşivdeki gün sayısı", gun_sayisi),
        ("", ""),
        ("Veri kaynakları", ""),
        ("Index, min miktar/tutar, adımlar, digit, funding, periyot, kaldıraç",
         "İlgili borsanın public API'si"),
        ("Derinlik +-1% ve Spread", "Order book'tan hesaplanır (ham dolar, etiket yok)"),
        ("Listeli sütunu", "Var = o borsadan veri geldi. Yok = perp listeli değil ya da o gün veri çekilemedi"),
        ("Perp hacim ve Open interest", "Günlük hacim verisinden"),
        ("Index kırılımı - Binance, OKX, Gate", "API (kaynak borsa + ağırlık)"),
        ("Index kırılımı - Bitget", "Net public endpoint bulunamadı, boş kalabilir"),
        ("Index kırılımı - Bybit", "Bybit yayınlamıyor (dinamik hesaplıyor), boş"),
        ("Index kırılımı - Hyperliquid", "Sabit formül, aşağıya bakınız"),
        ("", ""),
        ("Hyperliquid index formülü (dokümanlı, sabit)", ""),
        ("Yöntem", "AĞIRLIKLI MEDYAN (ağırlıklı ortalama DEĞİL) - ağırlıklar medyan oyudur"),
        ("Normal varlıklar (ana likidite dışarıda, örn. BTC)",
         "Binance 3, OKX 2, Bybit 2, Kraken 1, Kucoin 1, Gate 1, MEXC 1 - Hyperliquid hariç"),
        ("Ana likiditesi Hyperliquid'de olan varlıklar (örn. HYPE)",
         "Sadece Hyperliquid; dış kaynaklar yeterli likiditeye kadar dahil edilmez"),
        ("", ""),
        ("Elle girilen veriler", ""),
        ("manuel-kaldirac.csv", f"Binance max kaldıraç - {len(manuel_kaldirac)} varlık dolu"),
        ("manuel-funding.csv", f"Default funding (faiz bileşeni) - {len(manuel_funding)} borsa dolu"),
        ("Önemli", "Elle girilen değerler tarih bazlı değildir; tüm günlerde aynı görünür"),
        ("Default funding notu", "Binance, Bybit, OKX, Hyperliquid: %0.01/8sa (doğrulandı). Bitget, Gate: kullanıcı teyidi bekliyor"),
        ("", ""),
        ("Excel nasıl üretilir", ""),
        ("Yöntem", "Her çalıştırmada arşivden sıfırdan üretilir; dosyaya elle yazılanlar korunmaz"),
        ("Elle veri girmek için", "manuel-*.csv dosyalarını GitHub'da düzenle"),
    ]
    ws.cell(1, 1, "Notlar ve kaynaklar").font = Font(name="Arial", size=12, bold=True)
    r = 3
    for a, b in satirlar:
        ca = ws.cell(r, 1, a)
        cb = ws.cell(r, 2, b)
        ca.font = FONT_B if (a and not b) else FONT
        cb.font = FONT
        cb.alignment = Alignment(wrap_text=True, vertical="top")
        r += 1
    ws.column_dimensions["A"].width = 52
    ws.column_dimensions["B"].width = 78
    return ws


def main():
    cmc = load_json("cmc.json")
    if not cmc:
        print("! cmc.json bulunamadi. Once CMC verisi cekilmeli.")
        return 1

    gunler_kontrat = gunluk_kontrat_verisi()
    gunler_hacim = gunluk_hacim_verisi()
    manuel_kaldirac = load_manuel_kaldirac()
    manuel_funding = load_manuel_funding()

    if not gunler_kontrat:
        print("! Kontrat verisi yok (ne arsiv ne kontrat*.json). Excel yine de uretilecek, "
              "varlik sheet'leri bos olacak.")

    coins = sorted(cmc.get("coins", []), key=lambda c: c.get("rank") or 9999)
    ilk50 = [c["symbol"] for c in coins[:TOP_N]]

    # CMC ilk 50 degistiginde yeni varliklari manuel CSV'ye bos satir olarak ekle
    kaldirac_csv_tamamla(ilk50)

    wb = openpyxl.Workbook()
    sheet_cmc(wb, cmc)
    for sym in ilk50:
        sheet_varlik(wb, sym, gunler_kontrat, gunler_hacim, manuel_kaldirac, manuel_funding)
    sheet_notlar(wb, len(gunler_kontrat), manuel_kaldirac, manuel_funding)

    wb.save(OUT)
    print(f"[EXCEL] {OUT} yazildi.")
    print(f"  Sheet sayisi : {len(wb.sheetnames)} (1 CMC + {len(ilk50)} varlik + 1 Notlar)")
    print(f"  Arsiv gunu   : {len(gunler_kontrat)}")
    print(f"  Varliklar    : {', '.join(ilk50[:10])}{' ...' if len(ilk50) > 10 else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
