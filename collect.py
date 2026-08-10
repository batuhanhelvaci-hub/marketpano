"""
collect.py  -  MarketPano veri toplayici (3 sekmeli mimari)
============================================================

Bu script UC ayri "mod"da calisir ve UC ayri dosya uretir.
Boylece CMC verisi ile borsa verisi birbirine ASLA karismaz.

MODLAR:
  python collect.py cmc        -> cmc.json          (Sekme 1: CoinMarketCap)
  python collect.py github     -> borsa_github.json (6 borsa: OKX,MEXC,Bitget,Gate,KuCoin,Coinbase)
  python collect.py local      -> borsa_local.json  (Binance + Bybit, senin bilgisayarinda)
  python collect.py all        -> hepsini sirayla (test icin; tek makinede engel yoksa)

Mod verilmezse 'all' varsayilir.

Her mod ayni zamanda kendi arsivini gunluk olarak biriktirir:
  arsiv/cmc/YYYY-MM-DD.json
  arsiv/borsa/YYYY-MM-DD.json   (github + local birlesmis borsa anlik goruntusu)

API key:
  CMC key ortam degiskeninden okunur:  CMC_API_KEY
  (GitHub'da 'secret' olarak, yerelde guncelle.bat icinde set edilir.)
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests

# ----------------------------------------------------------------------------
# AYARLAR
# ----------------------------------------------------------------------------

TOP_N_ASSETS = 150
REQUEST_TIMEOUT = 20
USER_AGENT = "marketpano/2.0"
OI_LIMIT = 200

# CMC API KEY
# - GitHub'da: Settings > Secrets'taki CMC_API_KEY otomatik okunur (asagidaki bos kalsa da olur).
# - Kendi bilgisayarinda: asagidaki tirnaklarin arasina kendi key'ini YAPISTIR.
#   Ornek:  CMC_API_KEY_YEDEK = "a1b2c3d4-5678-90ef-ghij-klmnopqrstuv"
CMC_API_KEY_YEDEK = "fb77cbb63ef6425193c2ddbfddd20f13"

# Once ortam degiskeni (GitHub secret), o yoksa yukariya yazdigin key kullanilir.
CMC_API_KEY = os.environ.get("CMC_API_KEY", "") or CMC_API_KEY_YEDEK

# Hangi borsa hangi modda cekilir
GITHUB_EXCHANGES = ["Hyperliquid", "OKX", "Bitget", "Gate", "MEXC"]
LOCAL_EXCHANGES = ["Binance", "Bybit"]
ALL_EXCHANGES = ["Hyperliquid", "Binance", "OKX", "Bybit", "Bitget", "Gate", "MEXC"]

HEADERS = {"User-Agent": USER_AGENT}


# ----------------------------------------------------------------------------
# Kucuk yardimcilar
# ----------------------------------------------------------------------------

def get_json(url, params=None):
    """Bir URL'den JSON ceker. Hata olursa None doner, programi durdurmaz."""
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  ! Hata ({url}): {e}")
        return None


def to_float(x, default=0.0):
    """Gelen degeri guvenle float'a cevirir."""
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def base_from_symbol(sym):
    """
    Borsa sembolunden 'base' (ana coin) ve 'quote' (USDT/USDC) ayirir.
    Ornek: 'BTCUSDT' -> ('BTC', 'USDT'),  'BTC-USDC' -> ('BTC', 'USDC')
    Tanimadigi quote ise None doner.
    """
    s = sym.upper().replace("-", "").replace("_", "").replace("/", "")
    for quote in ("USDT", "USDC"):
        if s.endswith(quote) and len(s) > len(quote):
            return s[: -len(quote)], quote
    return None, None



# ----------------------------------------------------------------------------
# 2) SPOT borsalari  (her biri kendi sema)
#    Her fonksiyon su formatta liste doner:
#      {"base": "BTC", "quote": "USDT", "volume_usd": 123.4}
# ----------------------------------------------------------------------------

def spot_binance():
    rows = []
    data = get_json("https://api.binance.com/api/v3/ticker/24hr")
    if not data:
        return rows
    for t in data:
        base, quote = base_from_symbol(t.get("symbol", ""))
        if base and quote:
            rows.append({
                "base": base,
                "quote": quote,
                # quoteVolume = islem hacmi USDT/USDC cinsinden ~ USD
                "volume_usd": to_float(t.get("quoteVolume")),
            })
    return rows


def spot_okx():
    rows = []
    data = get_json("https://www.okx.com/api/v5/market/tickers", {"instType": "SPOT"})
    if not data or "data" not in data:
        return rows
    for t in data["data"]:
        base, quote = base_from_symbol(t.get("instId", ""))
        if base and quote:
            # volCcy24h = quote para birimi cinsinden hacim
            rows.append({
                "base": base,
                "quote": quote,
                "volume_usd": to_float(t.get("volCcy24h")),
            })
    return rows


def spot_bybit():
    rows = []
    data = get_json("https://api.bybit.com/v5/market/tickers", {"category": "spot"})
    if not data or "result" not in data:
        return rows
    for t in data["result"].get("list", []):
        base, quote = base_from_symbol(t.get("symbol", ""))
        if base and quote:
            rows.append({
                "base": base,
                "quote": quote,
                "volume_usd": to_float(t.get("turnover24h")),
            })
    return rows


def spot_mexc():
    rows = []
    data = get_json("https://api.mexc.com/api/v3/ticker/24hr")
    if not data:
        return rows
    for t in data:
        base, quote = base_from_symbol(t.get("symbol", ""))
        if base and quote:
            rows.append({
                "base": base,
                "quote": quote,
                "volume_usd": to_float(t.get("quoteVolume")),
            })
    return rows


def spot_bitget():
    rows = []
    data = get_json("https://api.bitget.com/api/v2/spot/market/tickers")
    if not data or "data" not in data:
        return rows
    for t in data["data"]:
        base, quote = base_from_symbol(t.get("symbol", ""))
        if base and quote:
            # quoteVolume = quote cinsinden hacim
            rows.append({
                "base": base,
                "quote": quote,
                "volume_usd": to_float(t.get("quoteVolume")),
            })
    return rows


def spot_gate():
    rows = []
    data = get_json("https://api.gateio.ws/api/v4/spot/tickers")
    if not data:
        return rows
    for t in data:
        # gate sembolu: "BTC_USDT"
        base, quote = base_from_symbol(t.get("currency_pair", ""))
        if base and quote:
            rows.append({
                "base": base,
                "quote": quote,
                "volume_usd": to_float(t.get("quote_volume")),
            })
    return rows


def spot_kucoin():
    rows = []
    data = get_json("https://api.kucoin.com/api/v1/market/allTickers")
    if not data or "data" not in data:
        return rows
    for t in data["data"].get("ticker", []):
        # kucoin sembolu: "BTC-USDT"
        base, quote = base_from_symbol(t.get("symbol", ""))
        if base and quote:
            rows.append({
                "base": base,
                "quote": quote,
                "volume_usd": to_float(t.get("volValue")),  # quote cinsinden
            })
    return rows


def spot_coinbase():
    """Coinbase: cogu parite USD/USDC, USDT azdir. Iki cagri gerekir."""
    rows = []
    products = get_json("https://api.exchange.coinbase.com/products")
    if not products:
        return rows
    # Sadece USDT/USDC pariteleri ile ilgileniyoruz
    wanted = [p for p in products
              if p.get("quote_currency") in ("USDT", "USDC")
              and p.get("status") == "online"]
    for p in wanted:
        pid = p.get("id")
        base = p.get("base_currency")
        quote = p.get("quote_currency")
        stats = get_json(f"https://api.exchange.coinbase.com/products/{pid}/stats")
        if stats:
            vol_base = to_float(stats.get("volume"))      # base cinsinden adet
            last = to_float(stats.get("last"))            # son fiyat
            rows.append({
                "base": base,
                "quote": quote,
                "volume_usd": vol_base * last,            # USD'ye cevir
            })
        time.sleep(0.05)  # nazik ol, rate-limit'e takilma
    return rows


SPOT_SOURCES = {
    "Binance": spot_binance,
    "OKX": spot_okx,
    "Bybit": spot_bybit,
    "MEXC": spot_mexc,
    "Bitget": spot_bitget,
    "Gate": spot_gate,
    "KuCoin": spot_kucoin,
    "Coinbase": spot_coinbase,
}


# ----------------------------------------------------------------------------
# 3) FUTURES (perp) borsalari - perp hacmi + open interest
#    Her fonksiyon su formatta dict doner (base coin -> degerler):
#      {"BTC": {"perp_volume_usd": 1.2, "open_interest_usd": 3.4}}
# ----------------------------------------------------------------------------

def perp_binance(top_bases):
    out = {}
    prices = {}  # base -> lastPrice (OI'yi USD'ye cevirmek icin)
    # Perp hacmi + fiyat (tek cagri)
    tickers = get_json("https://fapi.binance.com/fapi/v1/ticker/24hr")
    if tickers:
        for t in tickers:
            base, quote = base_from_symbol(t.get("symbol", ""))
            if base and quote == "USDT":
                out.setdefault(base, {})["perp_volume_usd"] = to_float(t.get("quoteVolume"))
                prices[base] = to_float(t.get("lastPrice"))
    # Open interest: Binance her sembol icin ayri cagri ister -> sadece buyukler.
    # Fiyat yukaridaki ticker'dan geldigi icin ayrica fiyat cagrisi YAPMIYORUZ (2 kat hizli).
    for base in top_bases:
        sym = f"{base}USDT"
        oi = get_json("https://fapi.binance.com/fapi/v1/openInterest", {"symbol": sym})
        if oi and "openInterest" in oi:
            price = prices.get(base, 0.0)
            out.setdefault(base, {})["open_interest_usd"] = to_float(oi["openInterest"]) * price
        time.sleep(0.03)
    return out


def perp_okx(top_bases):
    out = {}
    prices = {}  # base -> last price (USD'ye cevirmek icin)
    tickers = get_json("https://www.okx.com/api/v5/market/tickers", {"instType": "SWAP"})
    if tickers and "data" in tickers:
        for t in tickers["data"]:
            inst = t.get("instId", "")          # ornek: BTC-USDT-SWAP
            if inst.endswith("-USDT-SWAP"):
                base = inst.replace("-USDT-SWAP", "")
                last = to_float(t.get("last"))
                prices[base] = last
                # volCcy24h = base-coin cinsinden 24s hacim -> USD icin fiyatla carp
                vol_base = to_float(t.get("volCcy24h"))
                out.setdefault(base, {})["perp_volume_usd"] = vol_base * last
    # OKX open interest - oiCcy base-coin cinsinden -> fiyatla carp
    oi = get_json("https://www.okx.com/api/v5/public/open-interest", {"instType": "SWAP"})
    if oi and "data" in oi:
        for o in oi["data"]:
            inst = o.get("instId", "")
            if inst.endswith("-USDT-SWAP"):
                base = inst.replace("-USDT-SWAP", "")
                last = prices.get(base, 0)
                out.setdefault(base, {})["open_interest_usd"] = to_float(o.get("oiCcy")) * last
    return out


def perp_bybit(top_bases):
    out = {}
    data = get_json("https://api.bybit.com/v5/market/tickers", {"category": "linear"})
    if data and "result" in data:
        for t in data["result"].get("list", []):
            sym = t.get("symbol", "")
            base, quote = base_from_symbol(sym)
            if base and quote == "USDT":
                out.setdefault(base, {})["perp_volume_usd"] = to_float(t.get("turnover24h"))
                # openInterestValue zaten USD cinsinden gelir
                out[base]["open_interest_usd"] = to_float(t.get("openInterestValue"))
    return out


def perp_mexc(top_bases):
    """MEXC: contract/ticker hacim + OI verir.
    DIKKAT: holdVol KONTRAT cinsindedir. USD karsiligi icin
    contractSize (contract/detail'den) ve fiyatla carpilmalidir."""
    out = {}
    # kontrat carpanlari (tek cagri)
    carpan = {}
    det = get_json("https://contract.mexc.com/api/v1/contract/detail")
    if det and det.get("data"):
        for d in det["data"]:
            sym = d.get("symbol", "")
            if sym.endswith("_USDT"):
                carpan[sym[:-5]] = to_float(d.get("contractSize")) or 1.0
    data = get_json("https://contract.mexc.com/api/v1/contract/ticker")
    if data and "data" in data:
        for t in data["data"]:
            sym = t.get("symbol", "")            # ornek: BTC_USDT
            base, quote = base_from_symbol(sym)
            if base and quote == "USDT":
                fiyat = to_float(t.get("fairPrice")) or to_float(t.get("lastPrice"))
                cs = carpan.get(base, 1.0)
                oi_kontrat = to_float(t.get("holdVol"))
                out.setdefault(base, {})["perp_volume_usd"] = to_float(t.get("amount24"))
                out[base]["open_interest_usd"] = oi_kontrat * cs * fiyat if fiyat else None
    return out


def perp_bitget(top_bases):
    out = {}
    data = get_json("https://api.bitget.com/api/v2/mix/market/tickers",
                    {"productType": "usdt-futures"})
    if data and "data" in data:
        for t in data["data"]:
            sym = t.get("symbol", "")            # ornek: BTCUSDT
            base, quote = base_from_symbol(sym)
            if base and quote == "USDT":
                out.setdefault(base, {})["perp_volume_usd"] = to_float(t.get("usdtVolume"))
                # holdingAmount adet cinsinden; fiyatla carp
                price = to_float(t.get("lastPr"))
                out[base]["open_interest_usd"] = to_float(t.get("holdingAmount")) * price
    return out


def perp_gate(top_bases):
    out = {}
    # 1) Kontrat carpanlarini (quanto_multiplier) al: 1 kontrat = kac coin
    mult = {}
    contracts = get_json("https://api.gateio.ws/api/v4/futures/usdt/contracts")
    if contracts:
        for c in contracts:
            name = c.get("name", "")
            base, quote = base_from_symbol(name)
            if base and quote == "USDT":
                mult[base] = to_float(c.get("quanto_multiplier")) or 1.0
    # 2) tickers: volume_24h_quote = USDT hacim (dogru). OI = total_size * carpan * mark_price
    data = get_json("https://api.gateio.ws/api/v4/futures/usdt/tickers")
    if data:
        for t in data:
            name = t.get("contract", "")
            base, quote = base_from_symbol(name)
            if base and quote == "USDT":
                out.setdefault(base, {})["perp_volume_usd"] = to_float(t.get("volume_24h_quote"))
                mark = to_float(t.get("mark_price"))
                m = mult.get(base, 1.0)
                out[base]["open_interest_usd"] = to_float(t.get("total_size")) * m * mark
    return out


def perp_kucoin(top_bases):
    out = {}
    data = get_json("https://api-futures.kucoin.com/api/v1/contracts/active")
    if data and "data" in data:
        for c in data["data"]:
            sym = c.get("symbol", "")            # ornek: XBTUSDTM
            root = c.get("baseCurrency", "")
            # KuCoin BTC'yi "XBT" diye yazar -> duzelt
            base = "BTC" if root == "XBT" else root
            if c.get("quoteCurrency") == "USDT":
                vol = to_float(c.get("volumeOf24h"))
                price = to_float(c.get("markPrice") or c.get("lastTradePrice"))
                out.setdefault(base, {})["perp_volume_usd"] = vol * price
                out[base]["open_interest_usd"] = to_float(c.get("openInterest")) * price
    return out


def perp_coinbase(top_bases):
    # Coinbase'in perp urunu cogu bolgede sinirli/yok -> bos birakiyoruz.
    return {}


def perp_hyperliquid(top_bases):
    """Hyperliquid: POST /info ile metaAndAssetCtxs. Sadece USDC perp (DEX).
    Donen: her coin icin perp 24s hacim (USDC) + open interest (USD)."""
    out = {}
    try:
        r = requests.post(
            "https://api.hyperliquid.xyz/info",
            json={"type": "metaAndAssetCtxs"},
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"  ! Hyperliquid hatasi: {e}")
        return out
    # data = [meta, assetCtxs]  -> meta.universe[i].name <-> assetCtxs[i]
    if not (isinstance(data, list) and len(data) == 2):
        return out
    meta, ctxs = data[0], data[1]
    universe = (meta or {}).get("universe", [])
    for i, coin in enumerate(universe):
        if i >= len(ctxs):
            break
        base = (coin.get("name") or "").upper()
        c = ctxs[i] or {}
        # dayNtlVlm = gunluk notional hacim (USDC); openInterest adet -> markPx ile carp
        vol = to_float(c.get("dayNtlVlm"))
        oi_coins = to_float(c.get("openInterest"))
        mark = to_float(c.get("markPx"))
        out[base] = {
            "perp_volume_usd": vol,
            "open_interest_usd": oi_coins * mark,
        }
    return out


PERP_SOURCES = {
    "Hyperliquid": perp_hyperliquid,
    "Binance": perp_binance,
    "OKX": perp_okx,
    "Bybit": perp_bybit,
    "Bitget": perp_bitget,
    "Gate": perp_gate,
    "MEXC": perp_mexc,
}


# ----------------------------------------------------------------------------
# CoinMarketCap (Sekme 1 verisi)  -  sadece 'cmc' modunda calisir
# ----------------------------------------------------------------------------

def fetch_cmc(n):
    """CMC'den ilk n coin: fiyat, market cap, spot hacim (24s), 7d %."""
    if not CMC_API_KEY:
        print("  ! CMC_API_KEY yok. Veri cekilemiyor.")
        print("    GitHub'da secret olarak, yerelde guncelle.bat icinde key tanimla.")
        return []
    print(f"[CMC] ilk {n} coin cekiliyor...")
    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest"
    headers = {"X-CMC_PRO_API_KEY": CMC_API_KEY, "Accept": "application/json"}
    params = {"start": "1", "limit": str(n), "convert": "USD"}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        rows = r.json().get("data", [])
    except Exception as e:
        print(f"  ! CMC hatasi: {e}")
        return []
    out = []
    for c in rows:
        q = (c.get("quote") or {}).get("USD", {})
        out.append({
            "symbol": (c.get("symbol") or "").upper(),
            "name": c.get("name", ""),
            "rank": c.get("cmc_rank"),
            "price_usd": to_float(q.get("price")),
            "market_cap_usd": to_float(q.get("market_cap")),
            "spot_volume_24h_usd": to_float(q.get("volume_24h")),
            "percent_change_7d": to_float(q.get("percent_change_7d")),
        })
    print(f"  -> {len(out)} coin (CMC).")
    return out


# ----------------------------------------------------------------------------
# Coin listesi (borsa modlari icin hangi coinleri arayacagimiz)
# ----------------------------------------------------------------------------

def fetch_coin_list(n):
    """Borsa modlari icin sembol+rank listesi.
    CMC key varsa CMC'den (guncel ilk n), yoksa sabit yedek listeden alir.
    Boylece Binance/Bybit yerelde KEY OLMADAN da calisir."""
    coins = fetch_cmc(n)
    if coins:
        return [{"symbol": c["symbol"], "name": c["name"], "rank": c["rank"],
                 "market_cap_usd": c["market_cap_usd"]} for c in coins if c["symbol"]]
    # CMC yoksa sabit yedek liste (market cap'e gore yaklasik ilk 50)
    print("  ! CMC yok -> sabit yedek coin listesi kullaniliyor (key gerekmez).")
    yedek = ["BTC", "ETH", "USDT", "BNB", "SOL", "XRP", "USDC", "DOGE", "ADA",
             "TRX", "AVAX", "LINK", "TON", "SHIB", "DOT", "BCH", "LTC", "NEAR",
             "SUI", "APT", "HYPE", "ZEC", "XLM", "XMR", "LEO", "DAI", "CC",
             "USD1", "USDE", "UNI", "AAVE", "PEPE", "ETC", "OP", "ARB", "FIL",
             "ICP", "IMX", "INJ", "RENDER", "TAO", "FET", "ATOM", "STX", "GRT",
             "WIF", "SEI", "LDO", "MKR", "ONDO"]
    return [{"symbol": s, "name": s, "rank": i + 1, "market_cap_usd": 0}
            for i, s in enumerate(yedek[:n])]


# ----------------------------------------------------------------------------
# Borsa verisi toplama (secilen borsalar icin spot+perp+OI)
# ----------------------------------------------------------------------------

def collect_exchanges(which):
    """which: cekilecek borsa adlari listesi. Asset-bazli dict doner."""
    coins = fetch_coin_list(TOP_N_ASSETS)
    wanted = {c["symbol"] for c in coins}
    by_symbol = {c["symbol"]: {
        "symbol": c["symbol"], "name": c["name"], "rank": c["rank"],
        "market_cap_usd": c.get("market_cap_usd", 0), "exchanges": {}
    } for c in coins}

    top_bases = [c["symbol"] for c in sorted(coins, key=lambda x: x["rank"] or 9999)][:OI_LIMIT]

    def slot(base, exch):
        return by_symbol[base]["exchanges"].setdefault(
            exch, {"perp_volume_usd": 0.0, "open_interest_usd": 0.0})

    # PERP + OI (spot kaldirildi - artik sadece perp)
    for exch in which:
        fn = PERP_SOURCES.get(exch)
        if not fn:
            continue
        print(f"[PERP] {exch}...")
        for base, vals in fn(top_bases).items():
            if base in wanted:
                rec = slot(base, exch)
                rec["perp_volume_usd"] += vals.get("perp_volume_usd", 0.0)
                rec["open_interest_usd"] += vals.get("open_interest_usd", 0.0)

    return by_symbol


def write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def archive_daily(kind, payload):
    """Gunde 1 kayit: arsiv/<kind>/YYYY-MM-DD.json (ayni gun ustune yazar)."""
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    folder = os.path.join("arsiv", kind)
    os.makedirs(folder, exist_ok=True)
    write_json(os.path.join(folder, f"{day}.json"), payload)
    # indeks (gunlerin listesi)
    idx_path = os.path.join("arsiv", kind, "index.json")
    try:
        with open(idx_path) as f:
            idx = json.load(f)
    except Exception:
        idx = {"gunler": []}
    if day not in idx["gunler"]:
        idx["gunler"].append(day)
        idx["gunler"].sort()
    write_json(idx_path, idx)
    return day


# ----------------------------------------------------------------------------
# MODLAR
# ----------------------------------------------------------------------------

# ============================================================
#  BTCTURK SPOT LISTESI
#  Hangi varliklarin BtcTurk spot'ta listeli oldugunu ceker.
#  Excel'de borsa sayfalarina "BtcTurk Spot" (E/H) sutunu olarak yansir.
#  Kaynak: BtcTurk public API (kimlik dogrulama gerekmez).
# ============================================================

def run_btcturk_spot():
    """api.btcturk.com/api/v2/server/exchangeinfo -> btcturk_spot.json"""
    d = get_json("https://api.btcturk.com/api/v2/server/exchangeinfo")
    semboller = set()
    ciftler = 0
    if d and d.get("data"):
        for s_ in d["data"].get("symbols", []):
            if (s_.get("status") or "").upper() != "TRADING":
                continue
            base = s_.get("numerator")
            if base:
                semboller.add(str(base).upper())
                ciftler += 1
    if not semboller:
        print("  ! BtcTurk spot listesi cekilemedi.")
        return None
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "kaynak": "BtcTurk public API - exchangeinfo",
        "cift_sayisi": ciftler,
        "varliklar": sorted(semboller),
    }
    write_json("btcturk_spot.json", payload)
    print(f"[OK] btcturk_spot.json yazildi ({len(semboller)} varlik, {ciftler} cift).")
    return payload


def run_cmc():
    coins = fetch_cmc(TOP_N_ASSETS)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "kaynak": "CoinMarketCap",
        "coins": coins,
    }
    write_json("cmc.json", payload)
    day = archive_daily("cmc", payload)
    print(f"[OK] cmc.json yazildi + arsiv/cmc/{day}.json")


# ============================================================
#  GENIS KRIPTO LISTESI (hisse suzgeci)
#  Borsalar tokenize hisse/emtia perp'leri de listeliyor
#  (SNDK, SKHYNIX, SOXL, MU, XAU, KORU...). Bunlar kripto degil.
#  CMC'de olup olmadigina bakarak ayikliyoruz.
#  Ayrica bu liste hacim sheet'lerindeki Fiyat + Market Cap kaynagidir.
# ============================================================

WHITELIST_N = 1000       # CMC'den kac coin cekilecek (suzgec + fiyat/mcap icin)
GENIS_DOSYA = "cmc_genis.json"

# Borsalar dusuk fiyatli coinleri carpanli listeler:
#   Binance/Bybit : 1000PEPE, 1000SHIB, 1000BONK, 10000SATS, 1MBABYDOGE
#   Hyperliquid   : kPEPE, kSHIB, kBONK   (k = 1000)
# Bunlar GERCEK kriptodur; CMC'de sembol "PEPE" oldugu icin
# suzgecin bunlari hisse sanip atmasini engellemek gerekir.
_CARPAN_RE = re.compile(r"^(?:1000000|100000|10000|1000|100|10|1M|1B)([A-Z0-9]{2,})$")
_K_RE = re.compile(r"^k([A-Z]{2,})$")


def temel_sembol(sym):
    """Carpanli sembolun temel halini dondurur. Carpan yoksa None.
    1000PEPE -> PEPE | kPEPE -> PEPE | 1MBABYDOGE -> BABYDOGE
    1INCH, 0G, 2Z gibi gercek tickerlar etkilenmez (once tam eslesme denenir)."""
    if not sym:
        return None
    m = _CARPAN_RE.match(sym)
    if m:
        return m.group(1)
    m = _K_RE.match(sym)
    if m:
        return m.group(1)
    return None


# Kontrat aramasinda carpanli sembolleri de dene:
# CMC "PEPE" der ama borsa "1000PEPE" / "kPEPE" olarak listeler.
CARPAN_ONEKLERI = ["1000", "10000", "100000", "1000000", "1M", "k"]


def carpanli_ara(tablo, base):
    """tablo (borsanin sembol->veri sozlugu) icinde base'i, yoksa carpanli halini bulur.
    Doner: (bulunan_anahtar, deger) ya da (None, None)."""
    if base in tablo:
        return base, tablo[base]
    for on in CARPAN_ONEKLERI:
        aday = f"{on}{base}"
        if aday in tablo:
            return aday, tablo[aday]
    return None, None


def kripto_mu(sym, whitelist):
    """Sembol kripto mu? Once tam eslesme, sonra carpansiz hali denenir."""
    if not whitelist:
        return True          # suzgec yoksa hepsi gecer
    if sym in whitelist:
        return True
    t = temel_sembol(sym)
    return bool(t and t in whitelist)


def run_cmc_genis():
    """CMC ilk WHITELIST_N coin -> cmc_genis.json (+ gunluk arsiv)."""
    coins = fetch_cmc(WHITELIST_N)
    if not coins:
        print("  ! Genis CMC listesi cekilemedi.")
        return None
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "kaynak": "CoinMarketCap",
        "kapsam": f"ilk {WHITELIST_N} (kripto suzgeci + fiyat/mcap)",
        "coins": coins,
    }
    write_json(GENIS_DOSYA, payload)
    day = archive_daily("cmc_genis", payload)
    print(f"[OK] {GENIS_DOSYA} yazildi ({len(coins)} coin) + arsiv/cmc_genis/{day}.json")
    return payload


def kripto_semboller():
    """Kripto sembol kumesi. Sirasiyla dener:
       1) cmc_genis.json (bugune aitse)
       2) CMC'den taze cek (dosya yok/bayatsa) -> yazar
       3) cmc.json (son care, sadece ilk 150)
    Boylece bat, repodaki dosyalara muhtac olmadan calisir."""
    bugun = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    d = None
    try:
        with open(GENIS_DOSYA, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        d = None
    if not d or (d.get("generated_at") or "")[:10] != bugun:
        print(f"[SUZGEC] {GENIS_DOSYA} yok ya da bayat -> CMC'den cekiliyor...")
        d = run_cmc_genis() or d
    if not d:
        try:
            with open("cmc.json", encoding="utf-8") as f:
                d = json.load(f)
            print("[SUZGEC] cmc_genis alinamadi -> cmc.json kullaniliyor (sadece ilk 150).")
        except Exception:
            print("[SUZGEC] ! Kripto listesi bulunamadi. Hisse suzgeci UYGULANMAYACAK.")
            return None
    return {c["symbol"] for c in d.get("coins", [])}


def run_exchanges(which, outfile, etiket):
    data = collect_exchanges(which)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "kapsam": etiket,
        "exchanges": which,
        "assets": sorted(data.values(), key=lambda a: a.get("rank") or 9999),
    }
    write_json(outfile, payload)
    print(f"[OK] {outfile} yazildi ({etiket}: {', '.join(which)})")
    return payload


def merge_and_archive_borsa():
    """github + local borsa dosyalarini birlestirip gunluk borsa arsivi yazar.
    ONEMLI: local (Binance/Bybit) dosyasi SADECE bugune aitse arsive katilir.
    Eski (bayat) local, arsive gecmis gunun verisi gibi yazilmasin diye atlanir."""
    def load(p):
        try:
            with open(p) as f:
                return json.load(f)
        except Exception:
            return None
    def gun_of(src):
        # generated_at'tan YYYY-MM-DD kismini al
        try:
            return (src.get("generated_at") or "")[:10]
        except Exception:
            return ""
    bugun = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    g = load("borsa_github.json")
    l = load("borsa_local.json")
    # local bugune ait degilse arsive KATMA (bayat veri korumasi)
    if l and gun_of(l) != bugun:
        print(f"  ! borsa_local.json bayat ({gun_of(l)} != {bugun}) -> arsive katilmadi.")
        l = None
    merged = {}
    for src in (g, l):
        if not src:
            continue
        for a in src.get("assets", []):
            m = merged.setdefault(a["symbol"], {
                "symbol": a["symbol"], "name": a.get("name", ""),
                "rank": a.get("rank"), "market_cap_usd": a.get("market_cap_usd", 0),
                "exchanges": {}})
            m["exchanges"].update(a.get("exchanges", {}))
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "exchanges": ALL_EXCHANGES,
        "assets": sorted(merged.values(), key=lambda a: a.get("rank") or 9999),
    }
    if merged:
        archive_daily("borsa", payload)
    return payload


def merge_and_archive_kontrat():
    """kontrat_github.json + kontrat_local.json birlestirip gunluk kontrat arsivi yazar.
    Excel her gun bu arsivden sifirdan uretilir.
    ONEMLI: local (Binance/Bybit) dosyasi SADECE bugune aitse arsive katilir."""
    def load(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    def gun_of(src):
        try:
            return (src.get("generated_at") or "")[:10]
        except Exception:
            return ""
    bugun = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    g = load("kontrat_github.json")
    l = load("kontrat_local.json")
    if l and gun_of(l) != bugun:
        print(f"  ! kontrat_local.json bayat ({gun_of(l)} != {bugun}) -> arsive katilmadi.")
        l = None
    if not g and not l:
        print("  ! kontrat dosyasi bulunamadi, arsive yazilmadi.")
        return None
    merged = {}
    for src in (g, l):
        if not src:
            continue
        for a in src.get("assets", []):
            m = merged.setdefault(a["symbol"], {
                "symbol": a["symbol"], "name": a.get("name", ""),
                "rank": a.get("rank"), "exchanges": {}})
            m["exchanges"].update(a.get("exchanges", {}))
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "kapsam": f"Kontrat ozellikleri (CMC market cap ilk {KONTRAT_TOP_N})",
        "exchanges": ALL_EXCHANGES,
        "assets": sorted(merged.values(), key=lambda a: a.get("rank") or 9999),
    }
    if merged:
        archive_daily("kontrat", payload)
        print(f"  Kontrat arsivi yazildi ({len(merged)} varlik).")
    return payload


# ============================================================
#  KONTRAT OZELLIKLERI (yeni asama)
#  Her borsa, top-N pair icin: minQty, minNotional, tickSize,
#  digit, stepSize, maxLeverage, funding, orderbook derinlik+spread,
#  index price + agirlik kirilimi.
#  Sadece "kontrat" modunda calisir. kontrat.json yazar (arsive girmez).
# ============================================================

KONTRAT_TOP_N = 50   # hacmi en yuksek kac pair icin cekilecek

def digits_from_tick(tick):
    """tickSize'tan virgul sonrasi hane sayisini bulur. 0.001 -> 3, 0.1 -> 1, 1 -> 0"""
    try:
        from decimal import Decimal
        d = Decimal(str(tick)).normalize()
        exp = d.as_tuple().exponent
        return max(0, -exp) if isinstance(exp, int) else 0
    except Exception:
        return 0

def orderbook_depth_spread(bids, asks, mid, pct=0.01):
    """bids/asks: [[price, size], ...]. mid civari +-pct icindeki toplam USD derinlik + spread%."""
    try:
        if not bids or not asks or not mid or mid <= 0:
            return None, None
        best_bid = float(bids[0][0]); best_ask = float(asks[0][0])
        spread = (best_ask - best_bid) / mid * 100 if mid else None
        lo = mid * (1 - pct); hi = mid * (1 + pct)
        depth = 0.0
        for p, s in bids:
            p = float(p); s = float(s)
            if p >= lo:
                depth += p * s
        for p, s in asks:
            p = float(p); s = float(s)
            if p <= hi:
                depth += p * s
        return depth, spread
    except Exception:
        return None, None

def kontrat_bybit(top_bases):
    """Bybit: instruments (kurallar+kaldirac) + ticker (funding+fiyat) + orderbook (derinlik+spread)."""
    out = {}
    # 1) Instruments: kurallar + kaldirac
    #    ONEMLI: Bybit bu endpoint'te SAYFALAMA yapar (varsayilan 500 kayit).
    #    Bybit'te 700+ linear perp var; sayfalamazsak XRP, SOL, SUI gibi
    #    varliklar listenin disinda kalir. nextPageCursor ile tum sayfalar cekilir.
    kalemler = []
    imlec = None
    for _ in range(10):                       # guvenlik siniri
        par = {"category": "linear", "limit": 1000}
        if imlec:
            par["cursor"] = imlec
        inst = get_json("https://api.bybit.com/v5/market/instruments-info", par)
        if not inst or "result" not in inst:
            break
        kalemler.extend(inst["result"].get("list", []))
        imlec = inst["result"].get("nextPageCursor")
        if not imlec:
            break
        time.sleep(0.05)
    print(f"    Bybit instruments: {len(kalemler)} kayit")
    rules = {}
    if kalemler:
        for it in kalemler:
            base, quote = base_from_symbol(it.get("symbol", ""))
            if not base or quote != "USDT":
                continue
            pf = it.get("priceFilter", {}) or {}
            lf = it.get("lotSizeFilter", {}) or {}
            lev = it.get("leverageFilter", {}) or {}
            tick = pf.get("tickSize")
            rules[base] = {
                "min_qty": to_float(lf.get("minOrderQty")),
                "min_notional": to_float(lf.get("minNotionalValue")),
                "tick_size": to_float(tick),
                "digit": digits_from_tick(tick),
                "step_size": to_float(lf.get("qtyStep")),
                "max_leverage": to_float(lev.get("maxLeverage")),
                # Bybit fundingInterval DAKIKA cinsinden (480 = 8 saat)
                "funding_interval_h": (to_float(it.get("fundingInterval")) or 0) / 60.0 or None,
                "funding_cap": to_float(it.get("upperFundingRate")) or None,
            }
    # 2) Ticker: funding + mark/last fiyat (tek cagri)
    tick_data = {}
    tk = get_json("https://api.bybit.com/v5/market/tickers", {"category": "linear"})
    if tk and "result" in tk:
        for t in tk["result"].get("list", []):
            base, quote = base_from_symbol(t.get("symbol", ""))
            if base and quote == "USDT":
                tick_data[base] = {
                    "funding": to_float(t.get("fundingRate")),
                    "index_price": to_float(t.get("indexPrice")),
                    "mark_price": to_float(t.get("markPrice")),
                    "last": to_float(t.get("lastPrice")),
                }
    # 3) Sadece top_bases icin birlestir + orderbook (pair basi ayri cagri = yavas)
    for base in top_bases:
        gercek, r = carpanli_ara(rules, base)   # 1000PEPE / kPEPE gibi
        if not r:
            continue
        row = dict(r)
        row["borsa_sembolu"] = gercek
        td = tick_data.get(gercek, {})
        row["funding"] = td.get("funding")
        row["index_price"] = td.get("index_price")
        mid = td.get("mark_price") or td.get("last") or 0.0
        # orderbook derinlik + spread
        ob = get_json("https://api.bybit.com/v5/market/orderbook",
                      {"category": "linear", "symbol": f"{gercek}USDT", "limit": 50})
        if ob and "result" in ob:
            depth, spread = orderbook_depth_spread(
                ob["result"].get("b", []), ob["result"].get("a", []), mid)
            row["depth_1pct_usd"] = depth
            row["spread_pct"] = spread
        time.sleep(0.05)
        out[base] = row
    return out

def kontrat_binance(top_bases):
    """Binance: exchangeInfo (kurallar) + premiumIndex (funding+index) +
    constituents (index agirlik kirilimi) + orderbook (derinlik+spread)."""
    out = {}
    # 1) exchangeInfo: kurallar (tickSize, stepSize, minQty, minNotional) tek cagri
    info = get_json("https://fapi.binance.com/fapi/v1/exchangeInfo")
    rules = {}
    lev_map = {}
    if info and "symbols" in info:
        for s in info["symbols"]:
            if s.get("quoteAsset") != "USDT" or s.get("contractType") != "PERPETUAL":
                continue
            base = s.get("baseAsset")
            tick = step = min_qty = min_notional = None
            for f in s.get("filters", []):
                ft = f.get("filterType")
                if ft == "PRICE_FILTER":
                    tick = f.get("tickSize")
                elif ft == "LOT_SIZE":
                    step = f.get("stepSize"); min_qty = f.get("minQty")
                elif ft == "MIN_NOTIONAL":
                    min_notional = f.get("notional")
            rules[base] = {
                "min_qty": to_float(min_qty),
                "min_notional": to_float(min_notional),
                "tick_size": to_float(tick),
                "digit": digits_from_tick(tick),
                "step_size": to_float(step),
                "max_leverage": None,  # exchangeInfo'da yok, leverageBracket ayri (auth ister) -> bos
            }
    # 1b) fundingInfo: sadece VARSAYILANDAN FARKLI sozlesmeler listelenir.
    #     Listede olmayan sozlesme -> 8 saat (Binance varsayilani).
    finfo = get_json("https://fapi.binance.com/fapi/v1/fundingInfo")
    fmap = {}
    if isinstance(finfo, list):
        for fi in finfo:
            b, q = base_from_symbol(fi.get("symbol", ""))
            if b and q == "USDT":
                fmap[b] = {
                    "funding_interval_h": to_float(fi.get("fundingIntervalHours")) or None,
                    "funding_cap": to_float(fi.get("adjustedFundingRateCap")) or None,
                }
    # 2) premiumIndex: funding + index price (tek cagri, tum semboller)
    prem = get_json("https://fapi.binance.com/fapi/v1/premiumIndex")
    pmap = {}
    if isinstance(prem, list):
        for p in prem:
            base, quote = base_from_symbol(p.get("symbol", ""))
            if base and quote == "USDT":
                pmap[base] = {
                    "funding": to_float(p.get("lastFundingRate")),
                    "index_price": to_float(p.get("indexPrice")),
                    "mark_price": to_float(p.get("markPrice")),
                }
    # 3) top_bases icin birlestir + constituents (index agirlik) + orderbook
    for base in top_bases:
        gercek, r = carpanli_ara(rules, base)
        if not r:
            continue
        row = dict(r)
        row["borsa_sembolu"] = gercek
        pm = pmap.get(gercek, {})
        row["funding"] = pm.get("funding")
        fi = fmap.get(base, {})
        row["funding_interval_h"] = fi.get("funding_interval_h") or 8.0  # varsayilan 8 saat
        row["funding_cap"] = fi.get("funding_cap")
        row["index_price"] = pm.get("index_price")
        mid = pm.get("mark_price") or pm.get("index_price") or 0.0
        sym = f"{gercek}USDT"
        # index agirlik kirilimi (Binance constituents)
        cons = get_json("https://fapi.binance.com/fapi/v1/constituents", {"symbol": sym})
        if cons and "constituents" in cons:
            parts = []
            for c in cons["constituents"]:
                parts.append({
                    "exchange": c.get("exchange"),
                    "weight": to_float(c.get("weight")),
                    "price": to_float(c.get("price")),
                })
            row["index_breakdown"] = parts
        time.sleep(0.03)
        # orderbook derinlik + spread
        ob = get_json("https://fapi.binance.com/fapi/v1/depth", {"symbol": sym, "limit": 50})
        if ob and "bids" in ob:
            depth, spread = orderbook_depth_spread(ob.get("bids", []), ob.get("asks", []), mid)
            row["depth_1pct_usd"] = depth
            row["spread_pct"] = spread
        time.sleep(0.03)
        out[base] = row
    return out

def kontrat_okx(top_bases):
    """OKX: instruments (kurallar) + funding-rate + index-components (agirlik) + books.
    NOT: OKX'te minSz kontrat cinsinden; gercek coin = minSz * ctVal."""
    out = {}
    # 1) instruments (tum SWAP) - tek cagri
    inst = get_json("https://www.okx.com/api/v5/public/instruments", {"instType": "SWAP"})
    rules = {}
    if inst and inst.get("data"):
        for it in inst["data"]:
            if it.get("settleCcy") != "USDT":
                continue
            # instId: BTC-USDT-SWAP -> base BTC
            parts = (it.get("instId") or "").split("-")
            if len(parts) < 2:
                continue
            base = parts[0]
            tick = it.get("tickSz")
            ctval = to_float(it.get("ctVal")) or 1.0
            lot = to_float(it.get("lotSz")) or 1.0
            minsz = to_float(it.get("minSz")) or 0.0
            rules[base] = {
                "instId": it.get("instId"),
                "ctval": ctval,
                "min_qty": minsz * ctval,          # gercek coin cinsinden
                "min_notional": None,               # OKX ayri vermiyor; fiyatla hesaplanabilir
                "tick_size": to_float(tick),
                "digit": digits_from_tick(tick),
                "step_size": lot * ctval,           # miktar adimi coin cinsinden
                "max_leverage": to_float(it.get("lever")),
            }
    # 2) mark/index price (tum SWAP) - mark-price endpoint
    mp = get_json("https://www.okx.com/api/v5/public/mark-price", {"instType": "SWAP"})
    markmap = {}
    if mp and mp.get("data"):
        for m in mp["data"]:
            parts = (m.get("instId") or "").split("-")
            if len(parts) >= 2 and m.get("instId", "").endswith("-SWAP"):
                markmap[parts[0]] = to_float(m.get("markPx"))
    # 3) top_bases icin: funding + index-components + orderbook
    for base in top_bases:
        gercek, r = carpanli_ara(rules, base)
        if not r:
            continue
        row = dict(r); row.pop("instId", None); row.pop("ctval", None)
        row["borsa_sembolu"] = gercek
        instId = r["instId"]
        mark = markmap.get(gercek, 0.0)
        row["index_price"] = mark
        if r.get("min_notional") is None and mark:
            row["min_notional"] = r["min_qty"] * mark   # min coin * fiyat = min $
        # funding
        fr = get_json("https://www.okx.com/api/v5/public/funding-rate", {"instId": instId})
        if fr and fr.get("data"):
            d0 = fr["data"][0]
            row["funding"] = to_float(d0.get("fundingRate"))
            # OKX periyodu alan olarak vermiyor: nextFundingTime - fundingTime (ms)
            try:
                nf = float(d0.get("nextFundingTime") or 0)
                cf = float(d0.get("fundingTime") or 0)
                if nf > cf > 0:
                    row["funding_interval_h"] = round((nf - cf) / 3600000.0, 2)
            except Exception:
                pass
        time.sleep(0.03)
        # index agirlik kirilimi
        idxId = "-".join(instId.split("-")[:2])  # BTC-USDT
        ic = get_json("https://www.okx.com/api/v5/market/index-components", {"index": idxId})
        if ic and ic.get("data"):
            comps = ic["data"].get("components", []) if isinstance(ic["data"], dict) else []
            parts = []
            for c in comps:
                parts.append({"exchange": c.get("exch"), "weight": to_float(c.get("wgt")),
                              "price": to_float(c.get("prpx") or c.get("px"))})
            if parts:
                row["index_breakdown"] = parts
        time.sleep(0.03)
        # orderbook
        ob = get_json("https://www.okx.com/api/v5/market/books", {"instId": instId, "sz": 50})
        if ob and ob.get("data"):
            d0 = ob["data"][0]
            # OKX book elemani: [price, qty, ...]; qty kontrat cinsinden -> coin icin ctVal
            bids = [[p[0], to_float(p[1]) * r["ctval"]] for p in d0.get("bids", [])]
            asks = [[p[0], to_float(p[1]) * r["ctval"]] for p in d0.get("asks", [])]
            depth, spread = orderbook_depth_spread(bids, asks, mark)
            row["depth_1pct_usd"] = depth
            row["spread_pct"] = spread
        time.sleep(0.03)
        out[base] = row
    return out

def kontrat_gate(top_bases):
    """Gate: futures/usdt/contracts (kurallar+funding+mark+index) + order_book.
    NOT: Gate'te miktar 'kontrat' cinsinden; 1 kontrat = quanto_multiplier coin."""
    out = {}
    contracts = get_json("https://api.gateio.ws/api/v4/futures/usdt/contracts")
    cmap = {}
    if isinstance(contracts, list):
        for c in contracts:
            name = c.get("name", "")  # BTC_USDT
            if not name.endswith("_USDT"):
                continue
            base = name[:-5]
            mult = to_float(c.get("quanto_multiplier")) or 1.0
            tick = c.get("order_price_round")
            osize_min = to_float(c.get("order_size_min")) or 1.0
            mark = to_float(c.get("mark_price"))
            cmap[base] = {
                "name": name, "mult": mult, "mark": mark,
                "min_qty": osize_min * mult,
                "min_notional": (osize_min * mult * mark) if mark else None,
                "tick_size": to_float(tick),
                "digit": digits_from_tick(tick),
                "step_size": mult,   # en kucuk miktar adimi = 1 kontrat = mult coin
                "max_leverage": to_float(c.get("leverage_max")),
                "funding": to_float(c.get("funding_rate")),
                # Gate funding_interval SANIYE cinsinden (28800 = 8 saat)
                "funding_interval_h": (to_float(c.get("funding_interval")) or 0) / 3600.0 or None,
                "index_price": to_float(c.get("index_price")) or mark,
            }
    for base in top_bases:
        gercek, r = carpanli_ara(cmap, base)
        if not r:
            continue
        r = dict(r); r["borsa_sembolu"] = gercek
        name = r["name"]; mult = r["mult"]; mark = r["mark"] or r["index_price"]
        row = {k: r[k] for k in ("min_qty","min_notional","tick_size","digit","step_size",
                                 "max_leverage","funding","funding_interval_h","index_price")}
        # orderbook
        ob = get_json("https://api.gateio.ws/api/v4/futures/usdt/order_book",
                      {"contract": name, "limit": 50})
        if ob and ("bids" in ob or "asks" in ob):
            # Gate book elemani: {"p": price, "s": size(kontrat)} ya da [p,s]
            def conv(side):
                res = []
                for it in ob.get(side, []):
                    if isinstance(it, dict):
                        res.append([it.get("p"), to_float(it.get("s")) * mult])
                    else:
                        res.append([it[0], to_float(it[1]) * mult])
                return res
            depth, spread = orderbook_depth_spread(conv("bids"), conv("asks"), mark)
            row["depth_1pct_usd"] = depth
            row["spread_pct"] = spread
        # Gate index kirilimi: /futures/usdt/index_constituents/{index}
        ic = get_json(f"https://api.gateio.ws/api/v4/futures/usdt/index_constituents/{name}")
        if ic:
            comps = ic.get("constituents") if isinstance(ic, dict) else None
            parts = []
            if comps:
                for c in comps:
                    ex = c.get("exchange") if isinstance(c, dict) else None
                    # Gate bazen exchange basina birden cok pair listeler
                    if ex:
                        parts.append({"exchange": ex, "weight": None, "price": None})
            if parts:
                row["index_breakdown"] = parts
        time.sleep(0.05)
        out[base] = row
    return out

def kontrat_bitget(top_bases):
    """Bitget: contracts (kurallar+kaldirac) + tickers (index+mark+funding) + merge-depth."""
    out = {}
    contracts = get_json("https://api.bitget.com/api/v2/mix/market/contracts",
                         {"productType": "usdt-futures"})
    cmap = {}
    if contracts and contracts.get("data"):
        for c in contracts["data"]:
            base = c.get("baseCoin")
            if not base or c.get("quoteCoin") != "USDT":
                continue
            # pricePlace + priceEndStep -> tickSize; pricePlace zaten digit
            pp = int(to_float(c.get("pricePlace")) or 0)
            end_step = to_float(c.get("priceEndStep")) or 1.0
            tick = end_step / (10 ** pp) if pp else end_step
            cmap[base] = {
                "min_qty": to_float(c.get("minTradeNum")),
                "min_notional": to_float(c.get("minTradeUSDT")),
                "tick_size": tick,
                "digit": pp,
                "step_size": to_float(c.get("sizeMultiplier")),
                "max_leverage": to_float(c.get("maxLever")),
                # Bitget fundInterval SAAT cinsinden ("8")
                "funding_interval_h": to_float(c.get("fundInterval")) or None,
            }
    # Fiyat + funding: tickers TEK cagrida tum semboller icin
    # indexPrice, markPrice, lastPr, fundingRate verir.
    # (Onceki symbol-price cagrisi sembol parametresi istiyordu, bos donuyordu.)
    pmap = {}
    tk = get_json("https://api.bitget.com/api/v2/mix/market/tickers",
                  {"productType": "usdt-futures"})
    if tk and tk.get("data"):
        for t in tk["data"]:
            sym = t.get("symbol", "")
            if not sym.endswith("USDT"):
                continue
            idx = to_float(t.get("indexPrice"))
            mrk = to_float(t.get("markPrice"))
            last = to_float(t.get("lastPr"))
            pmap[sym[:-4]] = {
                "index": idx or mrk or last or None,
                "mid": mrk or idx or last or None,
                "funding": to_float(t.get("fundingRate")),
            }
    for base in top_bases:
        gercek, r = carpanli_ara(cmap, base)
        if not r:
            continue
        row = dict(r)
        row["borsa_sembolu"] = gercek
        sym = f"{gercek}USDT"
        p = pmap.get(gercek) or {}
        row["index_price"] = p.get("index")
        row["funding"] = p.get("funding")
        mid = p.get("mid") or 0.0
        # orderbook (merge-depth) - fiyat yoksa derinlik/spread hesaplanmaz
        if mid > 0:
            ob = get_json("https://api.bitget.com/api/v2/mix/market/merge-depth",
                          {"symbol": sym, "productType": "usdt-futures", "limit": "50"})
            if ob and ob.get("data"):
                d = ob["data"]
                depth, spread = orderbook_depth_spread(d.get("bids", []), d.get("asks", []), mid)
                row["depth_1pct_usd"] = depth
                row["spread_pct"] = spread
            time.sleep(0.03)
        out[base] = row
    return out

# Hyperliquid index agirliklari SABIT (dokumanli, degismez).
# Bir coin hangi kaynak borsalarda varsa onlar devreye girer; yoksa dusulur.
# Hyperliquid oracle = agirlikli MEDYAN (ortalama degil). Resmi dokuman:
#   Binance 3, OKX 2, Bybit 2, Kraken 1, Kucoin 1, Gate IO 1, MEXC 1, Hyperliquid 1
# Iki kural:
#   - Ana spot likiditesi Hyperliquid'de olan varliklar (orn. HYPE): dis kaynaklar
#     yeterli likiditeye kadar DAHIL EDILMEZ -> sadece Hyperliquid.
#   - Ana spot likiditesi disarida olan varliklar (orn. BTC): Hyperliquid'in kendi
#     spot fiyati DAHIL EDILMEZ -> asagidaki 7 kaynak kullanilir.
HL_DIS_KAYNAKLAR = [
    ("binance", 3), ("okx", 2), ("bybit", 2), ("kraken", 1),
    ("kucoin", 1), ("gateio", 1), ("mexc", 1),
]
# Ana likiditesi Hyperliquid'de olan varliklar (dokumanda ornek: HYPE).
HL_NATIVE = {"HYPE"}

def hl_index_breakdown(base, oracle):
    """Hyperliquid icin sabit formullu index kirilimi (agirlikli medyan oylari)."""
    if base in HL_NATIVE:
        return [{"exchange": "hyperliquid", "weight": 1.0, "price": oracle}]
    total = sum(w for _, w in HL_DIS_KAYNAKLAR)
    return [{"exchange": ex, "weight": w / total, "price": oracle}
            for ex, w in HL_DIS_KAYNAKLAR]

def kontrat_hyperliquid(top_bases):
    """Hyperliquid (DEX): POST /info metaAndAssetCtxs + l2Book.
    Index kirilimi API'de yok -> sabit dokumanli agirliklar kullanilir."""
    out = {}
    try:
        r = requests.post("https://api.hyperliquid.xyz/info",
                          json={"type": "metaAndAssetCtxs"},
                          headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"  ! Hyperliquid kontrat hatasi: {e}")
        return out
    if not (isinstance(data, list) and len(data) >= 2):
        return out
    universe = data[0].get("universe", [])
    ctxs = data[1]
    istenen = set(top_bases)
    for i, u in enumerate(universe):
        hl_ad = u.get("name")          # HL "kPEPE" gibi yazar
        if not hl_ad or i >= len(ctxs):
            continue
        # kPEPE -> PEPE; carpan yoksa kendisi
        base = hl_ad if hl_ad in istenen else (temel_sembol(hl_ad) or hl_ad)
        if base not in istenen:
            continue
        c = ctxs[i]
        mark = to_float(c.get("markPx"))
        oracle = to_float(c.get("oraclePx")) or mark
        szdec = int(u.get("szDecimals") or 0)
        bd = hl_index_breakdown(base, oracle)
        row = {
            "min_qty": 10 ** (-szdec) if szdec else 1.0,   # en kucuk miktar adimi
            "min_notional": None,
            "tick_size": None,   # HL: max 5 significant figure kurali, sabit tick yok
            "digit": None,
            "step_size": 10 ** (-szdec) if szdec else 1.0,
            "max_leverage": to_float(u.get("maxLeverage")),
            "funding": to_float(c.get("funding")),
            "funding_interval_h": 1.0,   # HL: saatlik, dokumanli sabit
            "index_price": oracle,
            "index_breakdown": bd,
            "borsa_sembolu": hl_ad,
        }
        if row["min_qty"] and mark:
            row["min_notional"] = row["min_qty"] * mark
        # orderbook (l2Book)
        try:
            rb = requests.post("https://api.hyperliquid.xyz/info",
                               json={"type": "l2Book", "coin": hl_ad},
                               headers=HEADERS, timeout=REQUEST_TIMEOUT)
            lv = rb.json().get("levels", [])
            if len(lv) == 2:
                bids = [[x["px"], x["sz"]] for x in lv[0]]
                asks = [[x["px"], x["sz"]] for x in lv[1]]
                depth, spread = orderbook_depth_spread(bids, asks, mark or oracle)
                row["depth_1pct_usd"] = depth
                row["spread_pct"] = spread
        except Exception:
            pass
        time.sleep(0.05)
        out[base] = row
    return out

def kontrat_mexc(top_bases):
    """MEXC: contract/detail (kurallar+kaldirac+indexOrigin) + contract/ticker
    (index+funding) + contract/depth (derinlik+spread).
    NOT: minVol, volUnit ve depth KONTRAT cinsindedir; contractSize ile carpilir."""
    out = {}
    det = get_json("https://contract.mexc.com/api/v1/contract/detail")
    rules = {}
    if det and det.get("data"):
        for d in det["data"]:
            sym = d.get("symbol", "")
            if not sym.endswith("_USDT"):
                continue
            base = sym[:-5]
            cs = to_float(d.get("contractSize")) or 1.0
            tick = d.get("priceUnit")
            rules[base] = {
                "sym": sym,
                "cs": cs,
                "min_qty": (to_float(d.get("minVol")) or 0) * cs,
                "min_notional": None,          # MEXC ayri vermiyor, fiyatla hesaplanir
                "tick_size": to_float(tick),
                "digit": int(to_float(d.get("priceScale")) or digits_from_tick(tick)),
                "step_size": (to_float(d.get("volUnit")) or 1) * cs,
                "max_leverage": to_float(d.get("maxLeverage")),
                # MEXC index kaynak listesini veriyor (agirliksiz)
                "index_origin": d.get("indexOrigin") or [],
            }
    tk = get_json("https://contract.mexc.com/api/v1/contract/ticker")
    tmap = {}
    if tk and tk.get("data"):
        for t in tk["data"]:
            sym = t.get("symbol", "")
            if sym.endswith("_USDT"):
                tmap[sym[:-5]] = {
                    "index": to_float(t.get("indexPrice")),
                    "mid": to_float(t.get("fairPrice")) or to_float(t.get("lastPrice")),
                    "funding": to_float(t.get("fundingRate")),
                }
    for base in top_bases:
        gercek, r = carpanli_ara(rules, base)
        if not r:
            continue
        cs = r["cs"]; sym = r["sym"]
        row = {k: r[k] for k in ("min_qty", "min_notional", "tick_size", "digit",
                                 "step_size", "max_leverage")}
        row["borsa_sembolu"] = gercek
        t = tmap.get(gercek) or {}
        row["index_price"] = t.get("index")
        row["funding"] = t.get("funding")
        mid = t.get("mid") or t.get("index") or 0.0
        if row["min_qty"] and mid:
            row["min_notional"] = row["min_qty"] * mid
        # index kaynak listesi (agirliksiz) -> kirilim alanina isim olarak yaz
        kaynaklar = r.get("index_origin") or []
        if kaynaklar:
            row["index_breakdown"] = [{"exchange": str(k).title(), "weight": None,
                                       "price": None} for k in kaynaklar]
        # funding periyodu
        fr = get_json(f"https://contract.mexc.com/api/v1/contract/funding_rate/{sym}")
        if fr and fr.get("data"):
            row["funding_interval_h"] = to_float(fr["data"].get("collectCycle")) or 8.0
        time.sleep(0.03)
        # derinlik (kontrat cinsinden -> coin'e cevir)
        if mid > 0:
            # DIKKAT: MEXC varsayilan olarak 1500 seviye dondurur.
            # Diger borsalarla ayni olcu icin ilk 50 seviye kullanilir.
            ob = get_json(f"https://contract.mexc.com/api/v1/contract/depth/{sym}",
                          {"limit": 50})
            if ob and ob.get("data"):
                d0 = ob["data"]
                bids = [[x[0], to_float(x[1]) * cs] for x in (d0.get("bids") or [])[:50]]
                asks = [[x[0], to_float(x[1]) * cs] for x in (d0.get("asks") or [])[:50]]
                depth, spread = orderbook_depth_spread(bids, asks, mid)
                row["depth_1pct_usd"] = depth
                row["spread_pct"] = spread
            time.sleep(0.03)
        out[base] = row
    return out


# Hangi borsa hangi kontrat fonksiyonunu kullanacak
KONTRAT_FN = {
    "Bybit": kontrat_bybit,
    "Binance": kontrat_binance,
    "OKX": kontrat_okx,
    "Gate": kontrat_gate,
    "Bitget": kontrat_bitget,
    "Hyperliquid": kontrat_hyperliquid,
    "MEXC": kontrat_mexc,
}

def run_kontrat(which_exchanges=None, outfile="kontrat.json"):
    """CMC market cap ilk 50 pair icin kontrat ozelliklerini ceker.
    which_exchanges: cekilecek borsalar (None=hepsi). outfile: yazilacak dosya.
    ONEMLI: Pair listesi cmc.json'dan (market cap ilk 50) gelir; tum borsalar AYNI 50 pair."""
    if which_exchanges is None:
        which_exchanges = list(KONTRAT_FN.keys())
    def load(p):
        import os as _os
        aday = [p, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), p)]
        for yol in aday:
            try:
                with open(yol, encoding="utf-8") as f:
                    print(f"[KONTRAT] bulundu: {yol}")
                    return json.load(f)
            except FileNotFoundError:
                continue
            except Exception as e:
                print(f"[KONTRAT] {yol} okunamadi: {e}")
        print(f"[KONTRAT] BULUNAMADI: {p}")
        return None
    print(f"[KONTRAT] calisma dizini: {os.getcwd()}")

    # Pair listesi = CMC market cap ilk KONTRAT_TOP_N
    # cmc.json varsa ondan; YOKSA dogrudan CMC'den cekilir.
    # (Bat senin bilgisayarinda cmc.json olmadan da calisabilsin diye.)
    cmc = load("cmc.json")
    tops = []
    if cmc and cmc.get("coins"):
        coins = sorted(cmc["coins"], key=lambda c: c.get("rank") or 9999)[:KONTRAT_TOP_N]
        tops = [{"symbol": c["symbol"], "name": c.get("name", ""), "rank": c.get("rank")} for c in coins]
    else:
        print("[KONTRAT] cmc.json yok -> liste dogrudan CMC'den cekiliyor...")
        coins = fetch_cmc(KONTRAT_TOP_N)
        tops = [{"symbol": c["symbol"], "name": c.get("name", ""), "rank": c.get("rank")} for c in coins]
    top_bases = [t["symbol"] for t in tops]

    if not top_bases:
        print("[KONTRAT] ! Pair listesi olusturulamadi (cmc.json yok ve CMC'den de cekilemedi).")
        print("[KONTRAT] ! Internet baglantisi ve CMC anahtarini kontrol et.")
        payload = {"generated_at": datetime.now(timezone.utc).isoformat(),
                   "kapsam": f"Kontrat ozellikleri (CMC market cap ilk {KONTRAT_TOP_N})",
                   "exchanges": list(KONTRAT_FN.keys()), "assets": [],
                   "hata": "pair listesi olusturulamadi"}
        with open(outfile, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return payload

    print(f"[KONTRAT] CMC market cap ilk {len(top_bases)} pair icin cekiliyor...")

    assets = {}
    secili_fn = {e: fn for e, fn in KONTRAT_FN.items() if e in which_exchanges}
    for exch, fn in secili_fn.items():
        print(f"  - {exch} kontrat ozellikleri...")
        try:
            data = fn(top_bases)
            for base, row in data.items():
                a = assets.setdefault(base, {"symbol": base, "exchanges": {}})
                a["exchanges"][exch] = row
        except Exception as e:
            print(f"    ! {exch} hatasi: {e}")

    # rank/isim ekle
    out_assets = []
    for t in tops:
        a = assets.get(t["symbol"], {"symbol": t["symbol"], "exchanges": {}})
        a["name"] = t["name"]; a["rank"] = t["rank"]
        out_assets.append(a)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "kapsam": f"Kontrat ozellikleri (CMC market cap ilk {KONTRAT_TOP_N})",
        "exchanges": list(secili_fn.keys()),
        "assets": out_assets,
    }
    with open(outfile, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[KONTRAT] {outfile} yazildi ({len(out_assets)} pair, {len(secili_fn)} borsa).")
    return payload


# ============================================================
#  HACIM (yeni yapi): her borsanin KENDI perp hacmine gore ilk 150'si
#  CMC listesine gore FILTRELENMEZ. Her borsa kendi siralamasini tasir.
#  Excel'de borsa basina bir sheet olur.
# ============================================================

HACIM_TOP_N = 150      # Excel'de gosterilecek varlik sayisi (en guncel gunun ilk 150'si)
HACIM_KAYIT_N = 300    # ARSIVE kaydedilecek varlik sayisi.
                       # Neden daha genis: ilk 150'nin bilesimi her gun degisiyor.
                       # Sadece 150 saklarsak, bugun 150'de olan bir varlik dun
                       # 151. sirada oldugu icin gecmisi bos gorunur. 300 saklayip
                       # 150 gostererek bu delikleri kapatiyoruz.

def run_hacim(which_exchanges=None, outfile="hacim.json"):
    """Her borsa icin: tum USDT perp'leri cek, TOKENIZE HISSE/EMTIA'yi ayikla,
    kalan KRIPTO perp'leri o borsanin KENDI 24s hacmine gore sirala, ilk 150'yi al.
    Siralama CMC sirasi DEGIL - her borsanin kendi hacim sirasidir.
    CMC listesi sadece 'bu sembol kripto mu' suzgeci olarak kullanilir."""
    if which_exchanges is None:
        which_exchanges = ALL_EXCHANGES
    kripto = kripto_semboller()
    if kripto:
        print(f"[HACIM] kripto suzgeci aktif ({len(kripto)} sembol).")
    sonuc = {}
    for exch in which_exchanges:
        fn = PERP_SOURCES.get(exch)
        if not fn:
            continue
        print(f"[HACIM] {exch} - tum perp'ler cekiliyor...")
        try:
            tumu = fn([])          # bos liste: sadece hacim, OI yok (hizli)
        except Exception as e:
            print(f"    ! {exch} hatasi: {e}")
            continue
        if not tumu:
            print(f"    ! {exch} veri gelmedi.")
            continue
        ham_adet = len(tumu)
        # Hisse/emtia ayikla (CMC'de olmayan sembolleri dusur).
        # Carpanli semboller (1000PEPE, kPEPE) kripto sayilir, elenmez.
        if kripto:
            elenen = [b for b in tumu if not kripto_mu(b, kripto)]
            tumu = {b: v for b, v in tumu.items() if kripto_mu(b, kripto)}
            if elenen:
                ornek = ", ".join(sorted(elenen)[:6])
                print(f"    {len(elenen)} kripto-disi sembol elendi (orn: {ornek})")
        sirali = sorted(tumu.items(),
                        key=lambda kv: -(kv[1].get("perp_volume_usd") or 0))
        top = [b for b, v in sirali[:HACIM_KAYIT_N] if (v.get("perp_volume_usd") or 0) > 0]
        # Open interest sadece ilk 150 icin cekilir (Excel'de yalnizca guncel gun
        # OI gosteriyor); kalan 150 sembol icin hacim yeterli, gereksiz cagri yapilmaz.
        oi_liste = top[:HACIM_TOP_N]
        print(f"    {ham_adet} perp -> {len(tumu)} kripto -> {len(top)} kaydediliyor "
              f"(ilk {len(oi_liste)} icin open interest de)")
        try:
            detay = fn(oi_liste)   # OI dahil ikinci gecis
        except Exception as e:
            print(f"    ! {exch} OI gecisi hatasi: {e}")
            detay = {}
        satirlar = []
        for i, base in enumerate(top, 1):
            v = detay.get(base) or tumu.get(base) or {}
            satirlar.append({
                "sira": i,
                "symbol": base,
                "perp_volume_usd": v.get("perp_volume_usd") or tumu.get(base, {}).get("perp_volume_usd"),
                "open_interest_usd": v.get("open_interest_usd"),
            })
        sonuc[exch] = satirlar
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "kapsam": f"Her borsanin kendi 24s perp hacminde ilk {HACIM_TOP_N} (sadece kripto)",
        "borsalar": sonuc,
    }
    with open(outfile, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[HACIM] {outfile} yazildi ({len(sonuc)} borsa).")
    return payload


# ============================================================
#  GERIYE DONUK HACIM (hafta sonu bosluklarini doldurmak icin)
#  Binance ve Bybit'in KENDI API'lerinden gunluk mum + OI gecmisi.
#  Kaynak karismaz: ayni borsa, sadece farkli endpoint.
#  Pencere farki: normal kayit "o andaki son 24 saat",
#  buradaki "UTC gunu kapanisi". Excel'de Kaynak sutunuyla isaretlenir.
# ============================================================

GECMIS_GUN = 7        # kac gun geriye bakilacak
GECMIS_ADAY = 400     # siralamayi kurmak icin kac sembolun gecmisi cekilecek


def _gun_str(ms):
    try:
        return datetime.fromtimestamp(int(ms) / 1000, timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return None


def gecmis_binance(bases, gun_sayisi):
    """{gun: {base: {perp_volume_usd, open_interest_usd}}}
    klines[7] = quote asset volume (USDT). openInterestHist son 30 gunle sinirli."""
    out = {}
    n = len(bases)
    for i, base in enumerate(bases, 1):
        sym = f"{base}USDT"
        if i % 50 == 0:
            print(f"      Binance gecmis: {i}/{n}")
        kl = get_json("https://fapi.binance.com/fapi/v1/klines",
                      {"symbol": sym, "interval": "1d", "limit": gun_sayisi + 1})
        if isinstance(kl, list):
            for row in kl:
                gun = _gun_str(row[0])
                if gun:
                    out.setdefault(gun, {}).setdefault(base, {})["perp_volume_usd"] = to_float(row[7])
        time.sleep(0.02)
        oi = get_json("https://fapi.binance.com/futures/data/openInterestHist",
                      {"symbol": sym, "period": "1d", "limit": gun_sayisi + 1})
        if isinstance(oi, list):
            for row in oi:
                gun = _gun_str(row.get("timestamp"))
                if gun:
                    out.setdefault(gun, {}).setdefault(base, {})["open_interest_usd"] = \
                        to_float(row.get("sumOpenInterestValue"))
        time.sleep(0.02)
    return out


def gecmis_bybit(bases, gun_sayisi):
    """{gun: {base: {...}}}  kline[6] = turnover (USDT).
    open-interest KONTRAT cinsinden gelir -> o gunun kapanis fiyatiyla USD'ye cevrilir."""
    out = {}
    n = len(bases)
    for i, base in enumerate(bases, 1):
        sym = f"{base}USDT"
        if i % 50 == 0:
            print(f"      Bybit gecmis: {i}/{n}")
        kapanis = {}
        kl = get_json("https://api.bybit.com/v5/market/kline",
                      {"category": "linear", "symbol": sym, "interval": "D",
                       "limit": gun_sayisi + 1})
        if kl and kl.get("result"):
            for row in kl["result"].get("list", []):
                gun = _gun_str(row[0])
                if gun:
                    out.setdefault(gun, {}).setdefault(base, {})["perp_volume_usd"] = to_float(row[6])
                    kapanis[gun] = to_float(row[4])
        time.sleep(0.02)
        oi = get_json("https://api.bybit.com/v5/market/open-interest",
                      {"category": "linear", "symbol": sym, "intervalTime": "1d",
                       "limit": gun_sayisi + 1})
        if oi and oi.get("result"):
            for row in oi["result"].get("list", []):
                gun = _gun_str(row.get("timestamp"))
                px = kapanis.get(gun)
                miktar = to_float(row.get("openInterest"))
                if gun and px and miktar:
                    out.setdefault(gun, {}).setdefault(base, {})["open_interest_usd"] = miktar * px
        time.sleep(0.02)
    return out


def gecmis_mexc(bases, gun_sayisi):
    """MEXC gunluk mum: amount = USDT tutari.
    NOT: MEXC public API'de OPEN INTEREST GECMISI YOK (403). Sadece hacim doldurulur."""
    out = {}
    n = len(bases)
    for i, base in enumerate(bases, 1):
        if i % 50 == 0:
            print(f"      MEXC gecmis: {i}/{n}")
        d = get_json(f"https://contract.mexc.com/api/v1/contract/kline/{base}_USDT",
                     {"interval": "Day1"})
        veri = (d or {}).get("data") if isinstance(d, dict) else None
        if isinstance(veri, dict) and veri.get("time"):
            zaman = veri["time"]; tutar = veri.get("amount") or []
            for j in range(len(zaman)):
                gun = _gun_str(int(zaman[j]) * 1000)
                if gun and j < len(tutar):
                    out.setdefault(gun, {}).setdefault(base, {})["perp_volume_usd"] = to_float(tutar[j])
        time.sleep(0.03)
    return out


GECMIS_FN = {"Binance": gecmis_binance, "Bybit": gecmis_bybit, "MEXC": gecmis_mexc}


def run_hacim_gecmis(which_exchanges=None, gun_sayisi=GECMIS_GUN,
                     outfile="hacim_gecmis_local.json"):
    """Son gun_sayisi gunun gunluk hacim/OI kaydini cikarir.
    Siralama o gunun hacmine gore yapilir; aday sembol kumesi bugunun
    en yuksek hacimli GECMIS_ADAY sembolunden alinir."""
    if which_exchanges is None:
        which_exchanges = ["Binance", "Bybit"]
    kripto = kripto_semboller()
    gunler = {}
    for exch in which_exchanges:
        fn = PERP_SOURCES.get(exch)
        gfn = GECMIS_FN.get(exch)
        if not fn or not gfn:
            continue
        print(f"[GECMIS] {exch} - aday sembol kumesi belirleniyor...")
        try:
            tumu = fn([])
        except Exception as e:
            print(f"    ! {exch} hatasi: {e}")
            continue
        if kripto:
            tumu = {b: v for b, v in tumu.items() if kripto_mu(b, kripto)}
        adaylar = [b for b, v in sorted(tumu.items(),
                                        key=lambda kv: -(kv[1].get("perp_volume_usd") or 0))
                   ][:GECMIS_ADAY]
        print(f"    {len(adaylar)} sembolun son {gun_sayisi} gunu cekiliyor (biraz surer)...")
        try:
            tarihli = gfn(adaylar, gun_sayisi)
        except Exception as e:
            print(f"    ! {exch} gecmis hatasi: {e}")
            continue
        for gun, semboller in tarihli.items():
            sirali = sorted(semboller.items(),
                            key=lambda kv: -(kv[1].get("perp_volume_usd") or 0))
            satirlar = []
            for i, (base, v) in enumerate(sirali[:HACIM_KAYIT_N], 1):
                if not (v.get("perp_volume_usd") or 0) > 0:
                    continue
                satirlar.append({
                    "sira": i,
                    "symbol": base,
                    "perp_volume_usd": v.get("perp_volume_usd"),
                    "open_interest_usd": v.get("open_interest_usd"),
                    "geriye_donuk": True,
                })
            if satirlar:
                gunler.setdefault(gun, {})[exch] = satirlar
        print(f"    {len(tarihli)} gun hazirlandi.")
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "kapsam": f"Geriye donuk gunluk hacim (son {gun_sayisi} gun, gunluk mum)",
        "gunler": gunler,
    }
    with open(outfile, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[GECMIS] {outfile} yazildi ({len(gunler)} gun).")
    return payload


def arsivle_gecmis():
    """hacim_gecmis_local.json'daki gunleri arsive isler.
    SADECE EKSIK olani doldurur - mevcut kaydin uzerine YAZMAZ.
    Bu sayede her calistirmada guvenle tekrarlanabilir."""
    gunler_hepsi = {}
    for dosya in ("hacim_gecmis_local.json", "hacim_gecmis_github.json"):
        try:
            with open(dosya, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue
        for gun, borsalar in (d.get("gunler") or {}).items():
            gunler_hepsi.setdefault(gun, {}).update(borsalar)
    if not gunler_hepsi:
        print("  ! Geriye donuk dosya bulunamadi.")
        return None
    eklendi, atlandi = 0, 0
    for gun, borsalar in gunler_hepsi.items():
        yol = os.path.join("arsiv", "hacim", f"{gun}.json")
        mevcut = None
        if os.path.exists(yol):
            try:
                with open(yol, encoding="utf-8") as f:
                    mevcut = json.load(f)
            except Exception:
                mevcut = None
        if not mevcut:
            mevcut = {"generated_at": f"{gun}T00:00:00+00:00",
                      "kapsam": f"Her borsanin kendi 24s perp hacminde ilk {HACIM_TOP_N} (sadece kripto)",
                      "borsalar": {}}
        hedef = mevcut.setdefault("borsalar", {})
        for exch, satirlar in borsalar.items():
            if hedef.get(exch):
                atlandi += 1
                continue
            hedef[exch] = satirlar
            eklendi += 1
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(mevcut, f, ensure_ascii=False, indent=2)
    print(f"  Geriye donuk isleme: {eklendi} borsa-gun eklendi, {atlandi} mevcut kayit korundu.")
    return True


def merge_and_archive_hacim():
    """hacim_github.json + hacim_local.json birlestirip gunluk hacim arsivi yazar.
    local (Binance/Bybit) SADECE bugune aitse katilir (bayat veri korumasi)."""
    def load(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    bugun = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    g = load("hacim_github.json")
    l = load("hacim_local.json")
    if l and (l.get("generated_at") or "")[:10] != bugun:
        print(f"  ! hacim_local.json bayat -> arsive katilmadi.")
        l = None
    if not g and not l:
        print("  ! hacim dosyasi bulunamadi, arsive yazilmadi.")
        return None
    borsalar = {}
    for src in (g, l):
        if src:
            borsalar.update(src.get("borsalar", {}))
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "kapsam": f"Her borsanin kendi 24s perp hacminde ilk {HACIM_TOP_N}",
        "borsalar": borsalar,
    }
    archive_daily("hacim", payload)
    print(f"  Hacim arsivi yazildi ({len(borsalar)} borsa).")
    return payload


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    print("=" * 56)
    print(f"MarketPano collect.py  -  mod: {mode}")
    print("=" * 56)

    if mode == "cmc":
        run_cmc()
    elif mode == "btcturk_spot":
        run_btcturk_spot()
    elif mode == "cmc_genis":
        # Genis kripto listesi (ilk 1000): hisse suzgeci + fiyat/mcap kaynagi
        run_cmc_genis()
    elif mode == "github":
        run_exchanges(GITHUB_EXCHANGES, "borsa_github.json", "GitHub 6 borsa")
        merge_and_archive_borsa()
    elif mode == "local":
        run_exchanges(LOCAL_EXCHANGES, "borsa_local.json", "Yerel Binance+Bybit")
        merge_and_archive_borsa()
    elif mode == "arsivle":
        # Veri CEKMEZ. Mevcut borsa_github.json + borsa_local.json'u
        # birlestirip gunluk arsive 6 borsali tam kaydi yazar.
        # (borsa_local.json GitHub'a yuklenince otomatik calisir.)
        merge_and_archive_borsa()
    elif mode == "kontrat":
        # Tum borsalar (senin bilgisayarinda calisir, hepsine erisim var). kontrat.json.
        run_kontrat()
    elif mode == "kontrat_github":
        # GitHub'da erisilebilen 4 borsa. kontrat_github.json.
        run_kontrat(which_exchanges=["OKX", "Gate", "Bitget", "Hyperliquid", "MEXC"],
                    outfile="kontrat_github.json")
    elif mode == "kontrat_local":
        # Cografi engelli 2 borsa (senin bilgisayarindan). kontrat_local.json.
        run_kontrat(which_exchanges=["Binance", "Bybit"],
                    outfile="kontrat_local.json")
    elif mode == "hacim":
        # Tum borsalar, her biri kendi ilk 150'si (senin bilgisayarinda test icin).
        run_hacim()
    elif mode == "hacim_github":
        run_hacim(which_exchanges=["OKX", "Bitget", "Gate", "Hyperliquid"],
                  outfile="hacim_github.json")
    elif mode == "hacim_local":
        run_hacim(which_exchanges=["Binance", "Bybit"],
                  outfile="hacim_local.json")
    elif mode == "arsivle_yeni":
        # SADECE hacim arsivlenir (gun gun birikir).
        # Kontrat verisi TEK FOTOGRAFTIR, arsivlenmez ve her gun yenilenmez.
        merge_and_archive_hacim()
    elif mode == "hacim_gecmis_github":
        # MEXC GitHub'dan erisilebiliyor; gecmis hacmi burada doldurulur.
        run_hacim_gecmis(which_exchanges=["MEXC"], outfile="hacim_gecmis_github.json")
    elif mode == "hacim_gecmis_local":
        # Hafta sonu bosluklarini doldurmak icin: Binance+Bybit son 7 gun
        # gunluk mum + OI gecmisi (kendi API'lerinden).
        run_hacim_gecmis()
    elif mode == "arsivle_gecmis":
        # Geriye donuk kayitlari arsive isler (sadece eksik gunleri doldurur).
        arsivle_gecmis()
    elif mode == "all":
        run_cmc()
        run_exchanges(GITHUB_EXCHANGES, "borsa_github.json", "GitHub 6 borsa")
        run_exchanges(LOCAL_EXCHANGES, "borsa_local.json", "Yerel Binance+Bybit")
        merge_and_archive_borsa()
    else:
        print(f"Bilinmeyen mod: {mode}. Kullan: cmc|github|local|arsivle|kontrat|kontrat_github|kontrat_local|all")
        sys.exit(1)

    print("=" * 56)
    print("Bitti.")
    print("=" * 56)


if __name__ == "__main__":
    # Calisma dizinini bu dosyanin bulundugu klasore sabitle.
    # Boylece bat/komut nereden calistirilirsa calistirilsin,
    # borsa_local.json / cmc.json / arsiv hep DOGRU klasorde aranir/yazilir.
    try:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
    except Exception:
        pass
    main()
