import asyncio
from services.tasks import price_alerts, rsi_alerts, daily_pulse, funding_alerts, signal_alerts

INTERVAL = 60


async def check_watchlists(app):
    while True:
        await price_alerts.run(app)
        await rsi_alerts.run(app)
        await daily_pulse.run(app)
        await funding_alerts.run(app)
        await signal_alerts.run(app)
        await asyncio.sleep(INTERVAL)
