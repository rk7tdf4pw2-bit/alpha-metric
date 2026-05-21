import asyncio
import httpx

ENDPOINTS = [
    ("Spot fiyat  (market_data.py)", "https://api.binance.com/api/v3/ticker/price",    {"symbol": "BTCUSDT"}),
    ("Kline/RSI  (rsi.py)",          "https://api.binance.com/api/v3/klines",           {"symbol": "BTCUSDT", "interval": "1h", "limit": 2}),
    ("Funding    (funding.py)",       "https://fapi.binance.com/fapi/v1/premiumIndex",  {"symbol": "BTCUSDT"}),
]


async def test():
    async with httpx.AsyncClient(timeout=10) as client:
        for label, url, params in ENDPOINTS:
            print(f"\n── {label}")
            print(f"   URL: {url}")
            try:
                r = await client.get(url, params=params)
                data = r.json()
                if isinstance(data, dict):
                    # İlk 2 key'i göster
                    preview = {k: data[k] for k in list(data)[:2]}
                else:
                    preview = data[0] if data else []
                print(f"   Durum: {r.status_code} OK")
                print(f"   Yanıt: {preview}")
            except httpx.ConnectError as e:
                print(f"   HATA (DNS/Bağlantı): {e}")
            except httpx.TimeoutException:
                print(f"   HATA: Zaman aşımı (10s)")
            except Exception as e:
                print(f"   HATA: {e}")

    print("\n── DNS çözümleme testi")
    import socket
    for host in ["api.binance.com", "fapi.binance.com"]:
        try:
            ip = socket.gethostbyname(host)
            print(f"   {host} → {ip}")
        except socket.gaierror as e:
            print(f"   {host} → DNS HATASI: {e}")


asyncio.run(test())
