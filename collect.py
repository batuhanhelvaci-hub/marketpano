"""
collect.py
----------
Perpetual Futures listeleme arastirmasi icin veri toplayici.

Ne yapar:
  1. CoinGecko'dan ilk N asset'i ceker (marketcap, global 24s hacim).
  2. 8 borsanin SPOT ticker API'sinden USDT/USDC parite hacimlerini ceker.
  3. 8 borsanin FUTURES (perp) API'sinden perp hacmi + open interest ceker.
  4. Hepsini tek bir asset-bazli tabloda birlestirir.
  5. Sonucu dashboard'un okuyacagi bir data.json dosyasina yazar.

API key GEREKMEZ. Hepsi halka acik market-data endpoint'leri.

Calistirma:  python collect.py
Cikti:       data.json  (ayni klasore yazilir)
"""

import json
import time
from datetime import datetime, timezone

import requests

# ----------------------------------------------------------------------------
# AYARLAR  -  istersen burayi degistirirsin
# ----------------------------------------------------------------------------

TOP_N_ASSETS = 50          # CoinGecko'dan kac asset cekilecek
REQUEST_TIMEOUT = 20       # her API cagrisi icin saniye cinsinden zaman asimi
USER_AGENT = "perp-research/1.0"

# Open interest cekerken her sembol icin ayri cagri gereken borsalarda
# (Binance gibi) sadece marketcap'i en buyuk bu kadar asset icin OI cekilir.
# Boylece script makul surede biter.
OI_LIMIT = 60

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
# 1) CoinGecko - asset listesi + marketcap
# ----------------------------------------------------------------------------

def fetch_coingecko_assets(n):
    """Ilk n asset'i marketcap, global 24s hacim ile ceker."""
    print(f"[CoinGecko] ilk {n} asset cekiliyor...")
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": n,
        "page": 1,
    }
    data = get_json(url, params)
    assets = {}
    if not data:
        return assets
    for coin in data:
        sym = (coin.get("symbol") or "").upper()
        if not sym:
            continue
        assets[sym] = {
            "symbol": sym,
            "name": coin.get("name", sym),
            "rank": coin.get("market_cap_rank"),
            "market_cap_usd": to_float(coin.get("market_cap")),
            "global_volume_24h_usd": to_float(coin.get("total_volume")),
            "price_usd": to_float(coin.get("current_price")),
        }
    print(f"  -> {len(assets)} asset alindi.")
    return assets


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


PERP_SOURCES = {
    "Binance": perp_binance,
    "OKX": perp_okx,
    "Bybit": perp_bybit,
    "MEXC": perp_mexc,
    "Bitget": perp_bitget,
    "Gate": perp_gate,
    "KuCoin": perp_kucoin,
    "Coinbase": perp_coinbase,
}


# ----------------------------------------------------------------------------
# 4) Hepsini birlestir
# ----------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Perp listeleme arastirmasi - veri toplama basliyor")
    print("=" * 60)

    assets = fetch_coingecko_assets(TOP_N_ASSETS)
    if not assets:
        print("CoinGecko'dan veri alinamadi. Cikiliyor.")
        return

    # Ilgilendigimiz asset'ler (CoinGecko ilk N)
    wanted_bases = set(assets.keys())
    # OI cekecegimiz buyuk asset'ler (rank'e gore ilk OI_LIMIT)
    top_bases = sorted(
        assets.values(), key=lambda a: a.get("rank") or 9999
    )
    top_bases = [a["symbol"] for a in top_bases[:OI_LIMIT]]

    # Her asset icin bos borsa kayitlari hazirla
    for a in assets.values():
        a["exchanges"] = {}     # borsa adi -> {spot_usdt, spot_usdc, perp, oi}

    def slot(base, exch):
        rec = assets[base]["exchanges"].setdefault(
            exch, {"spot_usdt": 0.0, "spot_usdc": 0.0,
                   "perp_volume_usd": 0.0, "open_interest_usd": 0.0})
        return rec

    # --- SPOT ---
    for exch, fn in SPOT_SOURCES.items():
        print(f"[SPOT] {exch} cekiliyor...")
        rows = fn()
        hit = 0
        for r in rows:
            base = r["base"]
            if base in wanted_bases:
                rec = slot(base, exch)
                if r["quote"] == "USDT":
                    rec["spot_usdt"] += r["volume_usd"]
                elif r["quote"] == "USDC":
                    rec["spot_usdc"] += r["volume_usd"]
                hit += 1
        print(f"  -> {hit} eslesen parite")

    # --- FUTURES ---
    for exch, fn in PERP_SOURCES.items():
        print(f"[PERP] {exch} cekiliyor...")
        data = fn(top_bases)
        hit = 0
        for base, vals in data.items():
            if base in wanted_bases:
                rec = slot(base, exch)
                rec["perp_volume_usd"] += vals.get("perp_volume_usd", 0.0)
                rec["open_interest_usd"] += vals.get("open_interest_usd", 0.0)
                hit += 1
        print(f"  -> {hit} eslesen asset")

    # --- Toplamlar / turetilmis metrikler ---
    for a in assets.values():
        ex = a["exchanges"]
        a["total_spot_usdt"] = sum(v["spot_usdt"] for v in ex.values())
        a["total_spot_usdc"] = sum(v["spot_usdc"] for v in ex.values())
        a["total_perp_volume_usd"] = sum(v["perp_volume_usd"] for v in ex.values())
        a["total_open_interest_usd"] = sum(v["open_interest_usd"] for v in ex.values())
        # Kac borsada perp listeli?
        a["perp_exchange_count"] = sum(
            1 for v in ex.values() if v["perp_volume_usd"] > 0)
        a["spot_exchange_count"] = sum(
            1 for v in ex.values() if (v["spot_usdt"] + v["spot_usdc"]) > 0)

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "exchanges": list(SPOT_SOURCES.keys()),
        "assets": sorted(assets.values(), key=lambda a: a.get("rank") or 9999),
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print("=" * 60)
    print(f"Bitti. {len(assets)} asset 'data.json' dosyasina yazildi.")
    print("=" * 60)


if __name__ == "__main__":
    main()
