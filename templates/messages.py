def price_alert(symbol: str, price: str) -> str:
    return (
        f"⚠️ Alpha Metric\n\n"
        f"{symbol} hedef seviyeye ulaştı.\n\n"
        f"Güncel fiyat: {price}"
    )


def daily_pulse(price: str, rsi: float) -> str:
    if rsi < 30:
        comment = "Aşırı satış bölgesinde."
    elif rsi < 45:
        comment = "Piyasa baskı altında görünüyor."
    elif rsi <= 55:
        comment = "Piyasa nötr bölgede seyrediyor."
    elif rsi <= 70:
        comment = "Risk iştahı artıyor olabilir."
    else:
        comment = "Aşırı alım bölgesinde."

    return (
        f"⚠️ Alpha Metric\n\n"
        f"BTC RSI: {rsi}\n"
        f"Fiyat: {price}\n\n"
        f"{comment}"
    )


def funding_alert(rate: float, state: str) -> str:
    direction = {
        "long_crowded": "Long pozisyonlar aşırı kalabalıklaşıyor olabilir.",
        "short_crowded": "Short pozisyonlar aşırı kalabalıklaşıyor olabilir.",
    }[state]
    return (
        f"⚠️ Alpha Metric\n\n"
        f"BTC funding oranı kritik seviyeye ulaştı.\n\n"
        f"{direction}\n\n"
        f"Funding: {rate * 100:+.4f}%"
    )


def signal_alert(symbol: str, score_label: str, signals: list[str]) -> str:
    lines = "\n".join(f"• {s}" for s in signals)
    return (
        f"⚠️ Alpha Metric\n\n"
        f"{symbol} için birden fazla {score_label} sinyal oluşuyor.\n\n"
        f"{lines}\n\n"
        f"Piyasada volatilite artabilir."
    )


def rsi_alert(symbol: str, rsi: float, state: str) -> str:
    comment = {
        "oversold": "Aşırı satış bölgesine girilmiş olabilir.",
        "overbought": "Aşırı alım bölgesine girilmiş olabilir.",
    }[state]
    return (
        f"⚠️ Alpha Metric\n\n"
        f"{symbol} RSI: {rsi}\n\n"
        f"{comment}"
    )
