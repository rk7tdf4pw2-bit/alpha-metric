import asyncio
import httpx
from utils.logger import logger

TIMEOUT = 10


async def get(url: str, **kwargs) -> dict | list | None:
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.get(url, **kwargs)
                return response.json()
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            if attempt == 0:
                logger.warning(f"API bağlantı hatası, tekrar deneniyor... url={url} hata={e}")
                await asyncio.sleep(2)
            else:
                logger.error(f"API bağlantı başarısız: url={url} hata={e}")
        except Exception as e:
            logger.error(f"API beklenmeyen hata: url={url} hata={e}")
            return None
    return None
