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
import sys
import time
from datetime import datetime, timezone

import requests

# ----------------------------------------------------------------------------
# AYARLAR
# ----------------------------------------------------------------------------

TOP_N_ASSETS = 50
REQUEST_TIMEOUT = 20
USER_AGENT = "marketpano/2.0"
OI_LIMIT = 60

CMC_API_KEY = os.environ.get("CMC_API_KEY", "")

# Hangi borsa hangi modda cekilir
GITHUB_EXCHANGES = ["Hyperliquid", "OKX", "Bitget", "Gate"]
LOCAL_EXCHANGES = ["Binance", "Bybit"]
ALL_EXCHANGES = ["Hyperliquid", "Binance", "OKX", "Bybit", "Bitget", "Gate"]

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
    # Perp hacmi (tek cagri)
    tickers = get_json("https://fapi.binance.com/fapi/v1/ticker/24hr")
    if tickers:
        for t in tickers:
            base, quote = base_from_symbol(t.get("symbol", ""))
            if base and quote == "USDT":
                out.setdefault(base, {})["perp_volume_usd"] = to_float(t.get("quoteVolume"))
    # Open interest: Binance her sembol icin ayri cagri ister -> sadece buyukler
    for base in top_bases:
        sym = f"{base}USDT"
        oi = get_json("https://fapi.binance.com/fapi/v1/openInterest", {"symbol": sym})
        if oi and "openInterest" in oi:
            # OI adet cinsinden gelir; USD icin fiyatla carpmak gerekir.
            # Yaklasik USD degeri icin premiumIndex'ten markPrice cekiyoruz.
            mark = get_json("https://fapi.binance.com/fapi/v1/premiumIndex", {"symbol": sym})
            price = to_float(mark.get("markPrice")) if mark else 0.0
            out.setdefault(base, {})["open_interest_usd"] = to_float(oi["openInterest"]) * price
        time.sleep(0.03)
    return out


def perp_okx(top_bases):
    out = {}
    tickers = get_json("https://www.okx.com/api/v5/market/tickers", {"instType": "SWAP"})
    if tickers and "data" in tickers:
        for t in tickers["data"]:
            inst = t.get("instId", "")          # ornek: BTC-USDT-SWAP
            if inst.endswith("-USDT-SWAP"):
                base = inst.replace("-USDT-SWAP", "")
                out.setdefault(base, {})["perp_volume_usd"] = to_float(t.get("volCcy24h"))
    # OKX open interest - tek cagri ile hepsi gelir
    oi = get_json("https://www.okx.com/api/v5/public/open-interest", {"instType": "SWAP"})
    if oi and "data" in oi:
        for o in oi["data"]:
            inst = o.get("instId", "")
            if inst.endswith("-USDT-SWAP"):
                base = inst.replace("-USDT-SWAP", "")
                out.setdefault(base, {})["open_interest_usd"] = to_float(o.get("oiCcy"))
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
    out = {}
    data = get_json("https://contract.mexc.com/api/v1/contract/ticker")
    if data and "data" in data:
        for t in data["data"]:
            sym = t.get("symbol", "")            # ornek: BTC_USDT
            base, quote = base_from_symbol(sym)
            if base and quote == "USDT":
                out.setdefault(base, {})["perp_volume_usd"] = to_float(t.get("amount24"))
                out[base]["open_interest_usd"] = to_float(t.get("holdVol"))
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
    data = get_json("https://api.gateio.ws/api/v4/futures/usdt/contracts")
    if data:
        for c in data:
            name = c.get("name", "")             # ornek: BTC_USDT
            base, quote = base_from_symbol(name)
            if base and quote == "USDT":
                vol = to_float(c.get("trade_size"))   # alternatif alanlar olabilir
                price = to_float(c.get("last_price") or c.get("mark_price"))
                # volume_24h_quote varsa onu kullan
                qv = to_float(c.get("volume_24h_quote") or c.get("volume_24h_settle"))
                out.setdefault(base, {})["perp_volume_usd"] = qv
                # OI: position_size adet -> fiyatla carp
                out[base]["open_interest_usd"] = to_float(c.get("position_size")) * price
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
    """Borsa modlari icin sadece sembol+rank listesi lazim. Kaynak: CMC."""
    coins = fetch_cmc(n)  # ayni veriyi kullanir, sadece sembol/rank'i alacagiz
    return [{"symbol": c["symbol"], "name": c["name"], "rank": c["rank"],
             "market_cap_usd": c["market_cap_usd"]} for c in coins if c["symbol"]]


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
    """github + local borsa dosyalarini birlestirip gunluk borsa arsivi yazar."""
    def load(p):
        try:
            with open(p) as f:
                return json.load(f)
        except Exception:
            return None
    g = load("borsa_github.json")
    l = load("borsa_local.json")
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


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    print("=" * 56)
    print(f"MarketPano collect.py  -  mod: {mode}")
    print("=" * 56)

    if mode == "cmc":
        run_cmc()
    elif mode == "github":
        run_exchanges(GITHUB_EXCHANGES, "borsa_github.json", "GitHub 6 borsa")
        merge_and_archive_borsa()
    elif mode == "local":
        run_exchanges(LOCAL_EXCHANGES, "borsa_local.json", "Yerel Binance+Bybit")
        merge_and_archive_borsa()
    elif mode == "all":
        run_cmc()
        run_exchanges(GITHUB_EXCHANGES, "borsa_github.json", "GitHub 6 borsa")
        run_exchanges(LOCAL_EXCHANGES, "borsa_local.json", "Yerel Binance+Bybit")
        merge_and_archive_borsa()
    else:
        print(f"Bilinmeyen mod: {mode}. Kullan: cmc | github | local | all")
        sys.exit(1)

    print("=" * 56)
    print("Bitti.")
    print("=" * 56)


if __name__ == "__main__":
    main()
