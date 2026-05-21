import asyncio
import httpx
from utils.logger import logger

TIMEOUT = 10  # saniye


async def get(url: str, **kwargs) -> dict | list | None:
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.get(url, **kwargs)
                return response.json()
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            if attempt == 0:
                logger.warning(f"Binance API geçici hata, tekrar deneniyor... ({e})")
                await asyncio.sleep(2)
            else:
                logger.warning(f"Binance API başarısız: {e}")
    return None
