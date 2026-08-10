#!/usr/bin/env python3
"""
MEXC TEST - bagimsiz calisir, mevcut sisteme DOKUNMAZ.

Amac: MEXC'ten Binance icin aldigimiz verilerin AYNISINI alabiliyor muyuz?

Test edilenler:
  1) Erisim var mi (cografi engel)
  2) Kontrat kurallari: min miktar, min tutar, fiyat adimi, digit, miktar adimi, kaldirac
  3) Fiyat ve funding: index price, mark price, funding orani, funding periyodu
  4) Hacim ve open interest
  5) Order book: derinlik ve spread
  6) Index kaynak listesi
  7) GERIYE DONUK gunluk veri (hafta sonu doldurma icin)

Calistirma: python mexc-test.py
"""
import json
import time
from datetime import datetime, timezone

import requests

BASE = "https://contract.mexc.com/api/v1/contract"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; MarketPano/1.0)"}
TIMEOUT = 20
TEST_VARLIKLAR = ["BTC", "ETH", "SOL", "XRP", "PEPE", "DOGE"]


def cek(yol, params=None):
    url = f"{BASE}/{yol}"
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}"
        d = r.json()
        if not d.get("success", True):
            return None, f"API hata: {d.get('code')} {d.get('message')}"
        return d.get("data"), None
    except Exception as e:
        return None, str(e)


def baslik(n, ad):
    print()
    print("=" * 70)
    print(f"  {n}) {ad}")
    print("=" * 70)


def f(x, ondalik=8):
    if x is None:
        return "YOK"
    if isinstance(x, (int, float)):
        return f"{x:,.{ondalik}f}".rstrip("0").rstrip(".") if ondalik else f"{x:,.0f}"
    return str(x)


def main():
    print()
    print("#" * 70)
    print("#  MEXC ERISIM VE VERI TESTI")
    print(f"#  {datetime.now(timezone.utc).isoformat()}")
    print("#" * 70)

    # ---------- 1) ERISIM ----------
    baslik(1, "ERISIM TESTI")
    data, hata = cek("detail")
    if hata:
        print(f"  BASARISIZ: {hata}")
        print()
        print("  >> MEXC bu sunucudan ERISILEMIYOR.")
        print("  >> Binance/Bybit gibi yerel bilgisayardan cekilmesi gerekir.")
        return 1
    usdt = [d for d in data if str(d.get("symbol", "")).endswith("_USDT")]
    print(f"  BASARILI. Toplam kontrat: {len(data)} | USDT perp: {len(usdt)}")

    kurallar = {d["symbol"][:-5]: d for d in usdt}

    # ---------- 2) KONTRAT KURALLARI ----------
    baslik(2, "KONTRAT KURALLARI (Excel'deki sutunlarla ayni sirada)")
    for v in TEST_VARLIKLAR:
        d = kurallar.get(v)
        if not d:
            # carpanli olabilir
            aday = [k for k in kurallar if k.endswith(v) and k != v]
            if aday:
                print(f"  {v}: duz sembol yok, carpanli var -> {aday[:3]}")
                d = kurallar[aday[0]]
                v = aday[0]
            else:
                print(f"  {v}: KONTRAT YOK")
                continue
        cs = float(d.get("contractSize") or 1)
        print(f"  --- {v}_USDT ---")
        print(f"     kontrat carpani (contractSize) : {f(cs)}")
        print(f"     min miktar  (minVol x carpan)  : {f(float(d.get('minVol') or 0) * cs)}")
        print(f"     miktar adimi(volUnit x carpan) : {f(float(d.get('volUnit') or 0) * cs)}")
        print(f"     fiyat adimi (priceUnit)        : {f(d.get('priceUnit'))}")
        print(f"     digit       (priceScale)       : {d.get('priceScale')}")
        print(f"     max kaldirac(maxLeverage)      : {d.get('maxLeverage')}")
        print(f"     index kaynaklari (indexOrigin) : {d.get('indexOrigin')}")

    # ---------- 3) FIYAT / FUNDING / HACIM / OI ----------
    baslik(3, "TICKER: index, mark, funding, hacim, open interest")
    tick, hata = cek("ticker")
    if hata:
        print(f"  BASARISIZ: {hata}")
    else:
        tmap = {t["symbol"][:-5]: t for t in tick if str(t.get("symbol", "")).endswith("_USDT")}
        for v in TEST_VARLIKLAR:
            t = tmap.get(v)
            if not t:
                aday = [k for k in tmap if k.endswith(v) and k != v]
                if not aday:
                    print(f"  {v}: TICKER YOK")
                    continue
                v = aday[0]
                t = tmap[v]
            cs = float((kurallar.get(v) or {}).get("contractSize") or 1)
            fiyat = float(t.get("fairPrice") or t.get("lastPrice") or 0)
            oi_k = float(t.get("holdVol") or 0)
            print(f"  --- {v}_USDT ---")
            print(f"     index price (indexPrice)   : {f(t.get('indexPrice'), 4)}")
            print(f"     mark price  (fairPrice)    : {f(t.get('fairPrice'), 4)}")
            print(f"     funding     (fundingRate)  : {f(t.get('fundingRate'))}")
            print(f"     24s hacim   (amount24)     : {f(t.get('amount24'), 0)} USDT")
            print(f"     OI kontrat  (holdVol)      : {f(oi_k, 0)}")
            print(f"     OI dolar    (hesaplanan)   : {f(oi_k * cs * fiyat, 0)} USD")

    # ---------- 4) FUNDING PERIYODU ----------
    baslik(4, "FUNDING PERIYODU ve TAVAN/TABAN")
    for v in ["BTC", "ETH"]:
        d, hata = cek(f"funding_rate/{v}_USDT")
        if hata:
            print(f"  {v}: {hata}")
            continue
        print(f"  {v}_USDT -> periyot: {d.get('collectCycle')} saat | "
              f"funding: {d.get('fundingRate')} | "
              f"tavan: {d.get('maxFundingRate')} | taban: {d.get('minFundingRate')}")

    # ---------- 5) ORDER BOOK ----------
    baslik(5, "ORDER BOOK (derinlik + spread)")
    for v in ["BTC", "ETH"]:
        d, hata = cek(f"depth/{v}_USDT")
        if hata:
            print(f"  {v}: {hata}")
            continue
        bids = d.get("bids") or []
        asks = d.get("asks") or []
        if not bids or not asks:
            print(f"  {v}: bos order book")
            continue
        cs = float((kurallar.get(v) or {}).get("contractSize") or 1)
        bb, ba = float(bids[0][0]), float(asks[0][0])
        mid = (bb + ba) / 2
        lo, hi = mid * 0.99, mid * 1.01
        derin = sum(float(p) * float(q) * cs for p, q, *_ in bids if float(p) >= lo)
        derin += sum(float(p) * float(q) * cs for p, q, *_ in asks if float(p) <= hi)
        print(f"  {v}_USDT -> seviye: {len(bids)} alis / {len(asks)} satis")
        print(f"     en iyi alis/satis : {bb} / {ba}")
        print(f"     spread            : {(ba - bb) / mid * 100:.6f} %")
        print(f"     derinlik +-1%     : {derin:,.0f} USD")

    # ---------- 6) GERIYE DONUK VERI ----------
    baslik(6, "GERIYE DONUK GUNLUK VERI (hafta sonu doldurma icin)")
    for v in ["BTC", "ETH"]:
        d, hata = cek(f"kline/{v}_USDT", {"interval": "Day1"})
        if hata:
            print(f"  {v}: {hata}")
            continue
        if not isinstance(d, dict) or not d.get("time"):
            print(f"  {v}: beklenmeyen bicim -> {str(d)[:120]}")
            continue
        n = len(d["time"])
        print(f"  {v}_USDT -> {n} gunluk mum geldi")
        for i in range(max(0, n - 5), n):
            gun = datetime.fromtimestamp(d["time"][i], timezone.utc).strftime("%Y-%m-%d")
            print(f"     {gun}  kapanis={d['close'][i]}  "
                  f"hacim(vol)={d['vol'][i]:,.0f}  tutar(amount)={d['amount'][i]:,.0f}")
        print("     NOT: 'amount' USDT tutari ise geriye donuk hacim icin kullanilabilir.")

    # ---------- 7) OI GECMISI ----------
    baslik(7, "OPEN INTEREST GECMISI (varsa)")
    for yol in ["openInterest/BTC_USDT", "open_interest/BTC_USDT"]:
        d, hata = cek(yol)
        print(f"  {yol} -> {'HATA: ' + hata if hata else str(d)[:150]}")

    print()
    print("#" * 70)
    print("#  TEST BITTI")
    print("#" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
