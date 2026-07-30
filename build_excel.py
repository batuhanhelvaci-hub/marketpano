#!/usr/bin/env python3
"""
MarketPano - Excel uretici (genis format)
=========================================
Cikti: marketpano.xlsx

  Sheet 1-6    : Binance, OKX, Bybit, Bitget, Gate, Hyperliquid
                 A sutunu Varlik. Sonra her GUN icin 4 sutunluk blok:
                 Fiyat | Market Cap | Perp Hacim | Open Interest
                 Yeni gun SAGA eklenir. Tarih ve Sira sutunu yoktur.

  Sheet 7      : Total
                 A sutunu Varlik, sonraki sutunlar tarih.
                 Deger: o varligin 6 borsadaki TOPLAM perp hacmi.

  Sheet 8-57   : Her varlik icin ayri kontrat sheet'i (CMC ilk 50).
                 Satirlar borsalar alt alta (+ en altta BTCTURK).
                 Sutunlar 12 kontrat alani.

  Sonraki      : Analiz - Varlik | Borsa | 12 alan, filtreli tek tablo.
                 Filtreden varlik secince o varligin tum borsalari alt alta.

  Son          : Notlar

Girdiler (bu dosyanin klasorunde):
  arsiv/hacim/YYYY-MM-DD.json      (yoksa hacim*.json tek gun)
  arsiv/cmc_genis/YYYY-MM-DD.json  (yoksa arsiv/cmc, yoksa cmc_genis.json/cmc.json)
  kontrat_github.json + kontrat_local.json   (kontrat TEK FOTOGRAF)
  manuel-kaldirac.csv, manuel-funding.csv, manuel-btcturk.csv

Excel her calistirmada SIFIRDAN uretilir; dosyaya elle yazilanlar korunmaz.
Elle girilecek veriler manuel-*.csv dosyalarinda tutulur.
"""
import csv
import glob
import json
import os
import re

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

os.chdir(os.path.dirname(os.path.abspath(__file__)))

OUT = "marketpano.xlsx"
BORSA_SIRASI = ["Binance", "OKX", "Bybit", "Bitget", "Gate", "Hyperliquid"]
KENDI_BORSA = "BTCTURK"

# Hacim sheet'lerinde her gun icin tekrarlanan sutunlar
GUN_METRIK = ["Fiyat ($)", "Market Cap ($)", "Perp Hacim ($)", "Open Interest ($)"]

KONTRAT_SUTUNLAR = ["Index Price", "Min Miktar", "Min Tutar ($)", "Fiyat Adimi",
                    "Digit", "Miktar Adimi", "Max Kaldirac", "Funding %",
                    "Funding Periyot (saat)", "Derinlik +-1% ($)", "Spread %",
                    "Index Kirilimi"]

BORSA_RENK = {
    "Binance": "F0B90B", "OKX": "2B3139", "Bybit": "FF7A00",
    "Bitget": "7B61FF", "Gate": "E5402B", "Hyperliquid": "50D2C2",
    KENDI_BORSA: "003AFF",
}
BORSA_DOLGU = {
    "Binance": "FFFBF0", "OKX": "F2F3F5", "Bybit": "FFF6EE",
    "Bitget": "F6F3FF", "Gate": "FFF1EF", "Hyperliquid": "EFFBF9",
    KENDI_BORSA: "E6EDFF",
}

FONT = Font(name="Arial", size=10)
FONT_B = Font(name="Arial", size=10, bold=True)
HEAD_FONT = Font(name="Arial", size=10, bold=True, color="FFFFFF")
HEAD_FILL = PatternFill("solid", fgColor="003AFF")
ALT_FILL = PatternFill("solid", fgColor="EEF3FB")
ALT_FONT = Font(name="Arial", size=9, bold=True, color="35496B")
THIN = Side(style="thin", color="D6DEEA")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

_CARPAN_RE = re.compile(r"^(?:1000000|100000|10000|1000|100|10|1M|1B)([A-Z0-9]{2,})$")
_K_RE = re.compile(r"^k([A-Z]{2,})$")


# ---------------- yardimcilar ----------------

def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def temel_sembol(sym):
    """1000PEPE -> PEPE, kPEPE -> PEPE. Carpan yoksa None."""
    if not sym:
        return None
    m = _CARPAN_RE.match(sym) or _K_RE.match(sym)
    return m.group(1) if m else None


def gun_bicim(gun):
    """2026-07-30 -> 30.07.2026"""
    try:
        y, a, g = gun.split("-")
        return f"{g}.{a}.{y}"
    except Exception:
        return gun


def hacim_gunleri():
    """{gun: {borsa: [satirlar]}}  - arsiv yoksa eldeki dosyalardan tek gun."""
    gunler = {}
    for p in sorted(glob.glob("arsiv/hacim/*.json")):
        d = load_json(p)
        if d:
            gunler[os.path.basename(p)[:-5]] = d.get("borsalar") or {}
    if gunler:
        return gunler
    birlesik, gun = {}, None
    for p in ("hacim_github.json", "hacim_local.json", "hacim.json"):
        d = load_json(p)
        if not d:
            continue
        gun = gun or (d.get("generated_at") or "")[:10]
        birlesik.update(d.get("borsalar") or {})
    if birlesik and gun:
        print(f"  ! arsiv/hacim bos -> eldeki dosyalar tek gun olarak alindi ({gun}).")
        return {gun: birlesik}
    return {}


def cmc_gunleri():
    """{gun: {sembol: (fiyat, mcap)}} - once genis liste (1000), sonra 150."""
    gunler = {}
    for klasor in ("arsiv/cmc_genis", "arsiv/cmc"):
        for p in sorted(glob.glob(f"{klasor}/*.json")):
            d = load_json(p)
            if not d:
                continue
            gun = os.path.basename(p)[:-5]
            hedef = gunler.setdefault(gun, {})
            for c in d.get("coins", []):
                hedef.setdefault(c["symbol"], (c.get("price_usd"), c.get("market_cap_usd")))
    if gunler:
        return gunler
    for aday in ("cmc_genis.json", "cmc.json"):
        d = load_json(aday)
        if d:
            gun = (d.get("generated_at") or "")[:10]
            gunler[gun] = {c["symbol"]: (c.get("price_usd"), c.get("market_cap_usd"))
                           for c in d.get("coins", [])}
            break
    return gunler


def cmc_bak(cmc, gun, sembol):
    """O gunun fiyat+mcap'i. Gun yoksa en yakin onceki gun. Carpanli sembolde temel token."""
    def bak(tablo):
        if sembol in tablo:
            return tablo[sembol]
        t = temel_sembol(sembol)
        if t and t in tablo:
            return tablo[t]
        return None
    if gun in cmc:
        r = bak(cmc[gun])
        if r:
            return r
    for g in sorted((x for x in cmc if x <= gun), reverse=True):
        r = bak(cmc[g])
        if r:
            return r
    for g in sorted(cmc):
        r = bak(cmc[g])
        if r:
            return r
    return (None, None)


def kontrat_snapshot():
    """Kontrat TEK FOTOGRAF: kontrat_github.json + kontrat_local.json.
    Doner: (varlik listesi, {borsa: cekildigi_gun})"""
    birlesik, tarihler = {}, {}
    for p in ("kontrat_github.json", "kontrat_local.json", "kontrat.json"):
        d = load_json(p)
        if not d:
            continue
        gun = (d.get("generated_at") or "")[:10]
        for a in d.get("assets", []):
            rec = birlesik.setdefault(a["symbol"], {
                "symbol": a["symbol"], "rank": a.get("rank"), "exchanges": {}})
            if rec.get("rank") is None:
                rec["rank"] = a.get("rank")
            for borsa, v in (a.get("exchanges") or {}).items():
                rec["exchanges"][borsa] = v
                tarihler[borsa] = gun
    return sorted(birlesik.values(), key=lambda a: a.get("rank") or 9999), tarihler


def csv_oku(dosya, anahtar):
    """CSV -> {anahtar_degeri: satir_dict}"""
    out = {}
    try:
        with open(dosya, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                k = (row.get(anahtar) or "").strip().upper()
                if k:
                    out[k] = row
    except FileNotFoundError:
        pass
    return out


def sayi(x):
    try:
        s = str(x).strip().replace(",", ".")
        return float(s) if s else None
    except Exception:
        return None


def load_manuel_kaldirac():
    d = csv_oku("manuel-kaldirac.csv", "varlik")
    if not d:
        print("  ! manuel-kaldirac.csv yok -> Binance kaldirac bos kalacak.")
    return {k: sayi(v.get("max_kaldirac")) for k, v in d.items()
            if sayi(v.get("max_kaldirac")) is not None}


def kaldirac_csv_tamamla(semboller):
    mevcut = set(csv_oku("manuel-kaldirac.csv", "varlik").keys())
    eksik = [s for s in semboller if s not in mevcut]
    if not eksik:
        return
    yeni = not os.path.exists("manuel-kaldirac.csv")
    with open("manuel-kaldirac.csv", "a", encoding="utf-8") as f:
        if yeni:
            f.write("varlik,max_kaldirac\n")
        for s in eksik:
            f.write(f"{s},\n")
    print(f"  manuel-kaldirac.csv'ye {len(eksik)} varlik eklendi (bos).")


BTCTURK_ALANLAR = ["min_miktar", "min_tutar", "fiyat_adimi", "digit",
                   "miktar_adimi", "max_kaldirac", "funding_periyot"]


def load_btcturk():
    d = csv_oku("manuel-btcturk.csv", "varlik")
    if not d:
        print("  ! manuel-btcturk.csv yok -> BTCTURK satirlari bos gorunecek.")
    return d


def btcturk_csv_tamamla(semboller):
    mevcut = set(csv_oku("manuel-btcturk.csv", "varlik").keys())
    eksik = [s for s in semboller if s not in mevcut]
    if not eksik:
        return
    yeni = not os.path.exists("manuel-btcturk.csv")
    with open("manuel-btcturk.csv", "a", encoding="utf-8") as f:
        if yeni:
            f.write("varlik," + ",".join(BTCTURK_ALANLAR) + "\n")
        for s in eksik:
            f.write(s + "," * len(BTCTURK_ALANLAR) + "\n")
    print(f"  manuel-btcturk.csv'ye {len(eksik)} varlik eklendi (bos).")


def load_manuel_funding():
    d = csv_oku("manuel-funding.csv", "borsa")
    return {k.title() if k != "OKX" else "OKX": sayi(v.get("default_funding"))
            for k, v in d.items() if sayi(v.get("default_funding")) is not None}


def breakdown_text(bd):
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
        parts.append(str(ex) if w is None else f"{ex}:{(w * 100 if w <= 1 else w):.0f}%")
    return ", ".join(parts)


def kontrat_degerler(k, sym, manuel_kaldirac, borsa):
    """Bir borsanin kontrat satirindaki 12 deger."""
    kaldirac = k.get("max_leverage")
    if kaldirac is None and borsa == "Binance":
        kaldirac = manuel_kaldirac.get(sym)
    fund = k.get("funding")
    return [
        k.get("index_price"), k.get("min_qty"), k.get("min_notional"),
        k.get("tick_size"), k.get("digit"), k.get("step_size"), kaldirac,
        (fund * 100) if fund is not None else None,
        k.get("funding_interval_h"), k.get("depth_1pct_usd"),
        k.get("spread_pct"),          # collect.py bunu ZATEN yuzde verir
        breakdown_text(k.get("index_breakdown")),
    ]


def btcturk_degerler(satir):
    """BTCTURK satiri: elle girilen alanlar 12'lik duzene oturtulur."""
    if not satir:
        return [None] * 12
    return [
        None,                              # Index Price - yok
        sayi(satir.get("min_miktar")),
        sayi(satir.get("min_tutar")),
        sayi(satir.get("fiyat_adimi")),
        sayi(satir.get("digit")),
        sayi(satir.get("miktar_adimi")),
        sayi(satir.get("max_kaldirac")),
        None,                              # Funding % - yok
        sayi(satir.get("funding_periyot")),
        None, None, "",                    # derinlik, spread, kirilim - yok
    ]


def kontrat_bicim(ws, r, c0):
    """12'lik blogun sayi bicimleri (c0 = ilk sutun)."""
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


# ---------------- hacim sheet'leri (genis) ----------------

def sheet_hacim(wb, borsa, gunler, cmc, ilk=False):
    ws = wb.active if ilk else wb.create_sheet()
    ws.title = borsa
    ws.sheet_properties.tabColor = BORSA_RENK.get(borsa, "003AFF")

    gun_listesi = [g for g in sorted(gunler) if gunler[g].get(borsa)]
    # varlik -> {gun: satir}
    veri, geriye = {}, {}
    for g in gun_listesi:
        satirlar = gunler[g].get(borsa) or []
        geriye[g] = any(s.get("geriye_donuk") for s in satirlar)
        for s in satirlar:
            veri.setdefault(s["symbol"], {})[g] = s

    # Siralama: en son gunun hacmi (yoksa bilinen son hacim), azalan
    def anahtar(sym):
        for g in reversed(gun_listesi):
            s = veri[sym].get(g)
            if s and (s.get("perp_volume_usd") or 0) > 0:
                return -(s["perp_volume_usd"])
        return 0
    varliklar = sorted(veri.keys(), key=anahtar)

    # Baslik: A1:A2 Varlik, her gun 4 sutun birlesik
    ws.merge_cells(start_row=1, start_column=1, end_row=2, end_column=1)
    c = ws.cell(1, 1, "Varlik")
    c.fill = HEAD_FILL; c.font = HEAD_FONT; c.border = BORDER
    c.alignment = Alignment(horizontal="center", vertical="center")
    n = len(GUN_METRIK)
    for i, g in enumerate(gun_listesi):
        c0 = 2 + i * n
        ws.merge_cells(start_row=1, start_column=c0, end_row=1, end_column=c0 + n - 1)
        etiket = gun_bicim(g) + (" (mum)" if geriye.get(g) else "")
        hc = ws.cell(1, c0, etiket)
        hc.fill = HEAD_FILL; hc.font = HEAD_FONT; hc.border = BORDER
        hc.alignment = Alignment(horizontal="center", vertical="center")
        for j, m in enumerate(GUN_METRIK):
            sc = ws.cell(2, c0 + j, m)
            sc.fill = ALT_FILL; sc.font = ALT_FONT; sc.border = BORDER
            sc.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.freeze_panes = "B3"

    dolgu = PatternFill("solid", fgColor=BORSA_DOLGU.get(borsa, "FFFFFF"))
    r = 3
    for sym in varliklar:
        vc = ws.cell(r, 1, sym); vc.font = FONT_B; vc.border = BORDER
        for i, g in enumerate(gun_listesi):
            c0 = 2 + i * n
            s = veri[sym].get(g) or {}
            fiyat, mcap = cmc_bak(cmc, g, sym) if s else (None, None)
            vals = [fiyat, mcap, s.get("perp_volume_usd"), s.get("open_interest_usd")]
            for j, v in enumerate(vals):
                cell = ws.cell(r, c0 + j, v)
                cell.font = FONT; cell.border = BORDER; cell.fill = dolgu
            ws.cell(r, c0 + 0).number_format = '#,##0.########'
            for j in (1, 2, 3):
                ws.cell(r, c0 + j).number_format = '#,##0'
        r += 1

    ws.column_dimensions["A"].width = 13
    for i in range(len(gun_listesi)):
        for j, w in enumerate([14, 18, 18, 18]):
            ws.column_dimensions[get_column_letter(2 + i * n + j)].width = w
    if r > 3:
        ws.auto_filter.ref = f"A2:{get_column_letter(1 + len(gun_listesi) * n)}{r - 1}"
    return len(varliklar), len(gun_listesi)


def sheet_total(wb, gunler, cmc):
    """A: Varlik, B+: tarihler. Deger = 6 borsanin TOPLAM perp hacmi."""
    ws = wb.create_sheet(title="Total")
    ws.sheet_properties.tabColor = "0A9D57"
    gun_listesi = sorted(gunler)
    toplam = {}   # sym -> {gun: toplam}
    for g in gun_listesi:
        for borsa in BORSA_SIRASI:
            for s in (gunler[g].get(borsa) or []):
                v = s.get("perp_volume_usd") or 0
                if v:
                    d = toplam.setdefault(s["symbol"], {})
                    d[g] = d.get(g, 0) + v

    def anahtar(sym):
        for g in reversed(gun_listesi):
            if toplam[sym].get(g):
                return -toplam[sym][g]
        return 0
    varliklar = sorted(toplam.keys(), key=anahtar)

    basliklar = ["Varlik"] + [gun_bicim(g) for g in gun_listesi]
    for c, h in enumerate(basliklar, 1):
        cell = ws.cell(1, c, h)
        cell.fill = HEAD_FILL; cell.font = HEAD_FONT; cell.border = BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.freeze_panes = "B2"

    r = 2
    for sym in varliklar:
        vc = ws.cell(r, 1, sym); vc.font = FONT_B; vc.border = BORDER
        for i, g in enumerate(gun_listesi):
            cell = ws.cell(r, 2 + i, toplam[sym].get(g))
            cell.font = FONT; cell.border = BORDER
            cell.number_format = '#,##0'
        r += 1
    ws.column_dimensions["A"].width = 13
    for i in range(len(gun_listesi)):
        ws.column_dimensions[get_column_letter(2 + i)].width = 20
    if r > 2:
        ws.auto_filter.ref = f"A1:{get_column_letter(1 + len(gun_listesi))}{r - 1}"
    return len(varliklar)


# ---------------- kontrat sheet'leri ----------------

def sheet_kontrat_varlik(wb, kayit, tarihler, manuel_kaldirac, btcturk):
    """Bir varlik icin: satirlar borsalar (+BTCTURK), sutunlar 12 kontrat alani."""
    sym = kayit["symbol"]
    ws = wb.create_sheet(title=sym[:31])
    basliklar = ["Borsa", "Veri Tarihi"] + KONTRAT_SUTUNLAR
    for c, h in enumerate(basliklar, 1):
        cell = ws.cell(1, c, h)
        cell.fill = HEAD_FILL; cell.font = HEAD_FONT; cell.border = BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"

    r = 2
    for borsa in BORSA_SIRASI:
        k = (kayit.get("exchanges") or {}).get(borsa) or {}
        bc = ws.cell(r, 1, borsa); bc.font = FONT_B
        ws.cell(r, 2, tarihler.get(borsa) or "").font = FONT
        vals = kontrat_degerler(k, sym, manuel_kaldirac, borsa)
        for j, v in enumerate(vals):
            cell = ws.cell(r, 3 + j, v)
            cell.font = FONT
        dolgu = PatternFill("solid", fgColor=BORSA_DOLGU.get(borsa, "FFFFFF"))
        for c in range(1, len(basliklar) + 1):
            ws.cell(r, c).border = BORDER
            ws.cell(r, c).fill = dolgu
        kontrat_bicim(ws, r, 3)
        r += 1

    # Kendi borsan
    bc = ws.cell(r, 1, KENDI_BORSA); bc.font = FONT_B
    ws.cell(r, 2, "elle girilen").font = FONT
    for j, v in enumerate(btcturk_degerler(btcturk.get(sym))):
        ws.cell(r, 3 + j, v).font = FONT
    dolgu = PatternFill("solid", fgColor=BORSA_DOLGU[KENDI_BORSA])
    for c in range(1, len(basliklar) + 1):
        ws.cell(r, c).border = Border(left=THIN, right=THIN,
                                     top=Side(style="medium", color="003AFF"),
                                     bottom=Side(style="medium", color="003AFF"))
        ws.cell(r, c).fill = dolgu
    kontrat_bicim(ws, r, 3)

    for c, w in zip("AB", [13, 12]):
        ws.column_dimensions[c].width = w
    for j, w in enumerate([13, 11, 11, 11, 6, 11, 9, 10, 9, 15, 9, 34]):
        ws.column_dimensions[get_column_letter(3 + j)].width = w
    return r


def sheet_analiz(wb, varliklar, tarihler, manuel_kaldirac, btcturk):
    """Tek tablo: Varlik | Borsa | 12 alan. Filtreden varlik secilir."""
    ws = wb.create_sheet(title="Analiz")
    ws.sheet_properties.tabColor = "E6A100"
    basliklar = ["Varlik", "Borsa", "Veri Tarihi"] + KONTRAT_SUTUNLAR
    for c, h in enumerate(basliklar, 1):
        cell = ws.cell(1, c, h)
        cell.fill = HEAD_FILL; cell.font = HEAD_FONT; cell.border = BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.freeze_panes = "C2"

    r = 2
    for a in varliklar:
        sym = a["symbol"]
        for borsa in BORSA_SIRASI + [KENDI_BORSA]:
            ws.cell(r, 1, sym).font = FONT_B
            ws.cell(r, 2, borsa).font = FONT_B
            if borsa == KENDI_BORSA:
                ws.cell(r, 3, "elle girilen").font = FONT
                vals = btcturk_degerler(btcturk.get(sym))
            else:
                ws.cell(r, 3, tarihler.get(borsa) or "").font = FONT
                k = (a.get("exchanges") or {}).get(borsa) or {}
                vals = kontrat_degerler(k, sym, manuel_kaldirac, borsa)
            for j, v in enumerate(vals):
                ws.cell(r, 4 + j, v).font = FONT
            dolgu = PatternFill("solid", fgColor=BORSA_DOLGU.get(borsa, "FFFFFF"))
            for c in range(1, len(basliklar) + 1):
                ws.cell(r, c).border = BORDER
                ws.cell(r, c).fill = dolgu
            kontrat_bicim(ws, r, 4)
            r += 1

    for c, w in zip("ABC", [13, 13, 12]):
        ws.column_dimensions[c].width = w
    for j, w in enumerate([13, 11, 11, 11, 6, 11, 9, 10, 9, 15, 9, 34]):
        ws.column_dimensions[get_column_letter(4 + j)].width = w
    if r > 2:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(basliklar))}{r - 1}"
    return r - 2


# ---------------- notlar ----------------

def sheet_notlar(wb, hacim_gun, kontrat_tarihler, manuel_kaldirac, manuel_funding, btcturk):
    ws = wb.create_sheet(title="Notlar")
    ws.cell(1, 1, "MarketPano - notlar ve kaynaklar").font = Font(name="Arial", size=12, bold=True)
    satirlar = [
        ("Yapı", ""),
        ("Borsa sheet'leri (6 adet)",
         "A sütunu Varlık. Sonra her gün için 4 sütunluk blok: Fiyat, Market Cap, "
         "Perp Hacim, Open Interest. Yeni gün sağa eklenir."),
        ("Satır sıralaması", "En son günün perp hacmine göre azalan"),
        ("Kapsam", "O borsanın kendi 24 saatlik perp hacminde ilk 150 kripto varlığı"),
        ("Total sheet", "A sütunu Varlık, sonraki sütunlar tarih. Değer: 6 borsanın TOPLAM perp hacmi."),
        ("Varlık sheet'leri (50 adet)",
         "CMC ilk 50. Her sheet'te borsalar alt alta, sütunlar 12 kontrat alanı, en altta BTCTURK."),
        ("Analiz sheet'i",
         "Varlık | Borsa | 12 alan. Filtreden varlık seçince o varlığın tüm borsaları alt alta gelir."),
        ("Arşivdeki gün sayısı", f"{hacim_gun} gün"),
        ("", ""),
        ("Veri kaynakları", ""),
        ("Perp hacim ve Open Interest", "İlgili borsanın public API'si"),
        ("Fiyat ve Market Cap", "CoinMarketCap ilk 1000"),
        ("Kontrat alanları", "İlgili borsanın public API'si"),
        ("Derinlik +-1% ve Spread", "Order book'tan hesaplanır (ham dolar, etiket yok)"),
        ("Tarih başlığında (mum) yazıyorsa",
         "O gün o borsanın verisi geriye dönük dolduruldu: UTC günlük mum. "
         "Normal kayıtlar o andaki son 24 saattir. Aynı borsa, biraz farklı pencere."),
        ("", ""),
        ("Süzgeçler", ""),
        ("Hisse/emtia süzgeci",
         "Borsalar tokenize hisse ve emtia perp'leri de listeliyor (SNDK, SOXL, XAU, MU...). "
         "CMC'de olmadıkları için listeden çıkarılır; sadece kripto kalır."),
        ("Çarpanlı semboller",
         "Binance/Bybit 1000PEPE, 1000SHIB gibi; Hyperliquid kPEPE gibi listeler "
         "(1 kontrat = 1000 token). Kripto sayılır, elenmez. Fiyat/Market Cap temel "
         "token'dan alınır, böylece borsalar arası karşılaştırılabilir."),
        ("", ""),
        ("Kontrat verisi", ""),
        ("Güncelleme", "TEK FOTOĞRAF - her gün yenilenmez. 'MarketPano kontrat guncelle' akışı elle çalıştırılır."),
        ("Çekildiği tarih",
         " · ".join(f"{b}: {g}" for b, g in sorted(kontrat_tarihler.items())) or "veri yok"),
        ("Index kırılımı - Binance, OKX, Gate", "API'den (kaynak borsa + ağırlık)"),
        ("Index kırılımı - Bitget", "Net public endpoint bulunamadı, boş kalabilir"),
        ("Index kırılımı - Bybit", "Bybit yayınlamıyor (dinamik hesaplıyor), boş"),
        ("Index kırılımı - Hyperliquid", "Sabit formül, aşağıda"),
        ("Hyperliquid yöntemi", "AĞIRLIKLI MEDYAN (ortalama DEĞİL) - ağırlıklar medyan oyudur"),
        ("Hyperliquid - normal varlıklar (örn. BTC)",
         "Binance 3 (%27,3) · OKX 2 (%18,2) · Bybit 2 (%18,2) · Kraken 1 (%9,1) · "
         "Kucoin 1 (%9,1) · Gate 1 (%9,1) · MEXC 1 (%9,1) — Hyperliquid hariç"),
        ("Hyperliquid - ana likiditesi kendisinde olanlar (örn. HYPE)",
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
        ("manuel-kaldirac.csv", f"Binance max kaldıraç (API'de yok) - {len(manuel_kaldirac)} varlık dolu"),
        ("manuel-btcturk.csv", f"BTCTURK kendi kontrat değerleri - {len(btcturk)} varlık satırı"),
        ("manuel-funding.csv", "Default funding değerleri (borsa başına)"),
        ("Önemli", "Elle girilen değerler tarih bazlı değildir; her yerde aynı görünür"),
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
    ws.column_dimensions["B"].width = 95
    return ws


# ---------------- ana akis ----------------

def main():
    gunler = hacim_gunleri()
    cmc = cmc_gunleri()
    kontrat_varliklar, kontrat_tarihler = kontrat_snapshot()

    if not gunler and not kontrat_varliklar:
        print("! Ne hacim ne kontrat verisi bulundu. Once veri cekilmeli.")
        return 1

    semboller = [a["symbol"] for a in kontrat_varliklar]
    if semboller:
        kaldirac_csv_tamamla(semboller)
        btcturk_csv_tamamla(semboller)
    manuel_kaldirac = load_manuel_kaldirac()
    manuel_funding = load_manuel_funding()
    btcturk = load_btcturk()

    wb = openpyxl.Workbook()
    ozet = []
    for i, borsa in enumerate(BORSA_SIRASI):
        adet, gun_adet = sheet_hacim(wb, borsa, gunler, cmc, ilk=(i == 0))
        ozet.append(f"{borsa}:{adet}v/{gun_adet}g")
    total_adet = sheet_total(wb, gunler, cmc)
    for a in kontrat_varliklar:
        sheet_kontrat_varlik(wb, a, kontrat_tarihler, manuel_kaldirac, btcturk)
    analiz_satir = sheet_analiz(wb, kontrat_varliklar, kontrat_tarihler,
                                manuel_kaldirac, btcturk)
    sheet_notlar(wb, len(gunler), kontrat_tarihler, manuel_kaldirac,
                 manuel_funding, btcturk)

    wb.save(OUT)
    print(f"[EXCEL] {OUT} yazildi.")
    print(f"  Sheet sayisi   : {len(wb.sheetnames)}")
    print(f"  Borsa sheet'i  : {' | '.join(ozet)}")
    print(f"  Total          : {total_adet} varlik")
    print(f"  Varlik sheet'i : {len(kontrat_varliklar)}")
    print(f"  Analiz satir   : {analiz_satir}")
    print(f"  Hacim arsivi   : {len(gunler)} gun | cmc {len(cmc)} gun")
    print(f"  Kontrat tarihi : {kontrat_tarihler or '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
