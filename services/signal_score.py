RSI_THRESHOLD_LOW  = 30
RSI_THRESHOLD_HIGH = 70
FUNDING_THRESHOLD  = 0.0005

SCORE_LABELS = {1: "düşük", 2: "orta", 3: "güçlü"}


def compute(rsi: float, funding: float) -> tuple[int, list[str]]:
    active = []

    if rsi < RSI_THRESHOLD_LOW:
        active.append("RSI aşırı satış bölgesinde")
    elif rsi > RSI_THRESHOLD_HIGH:
        active.append("RSI aşırı alım bölgesinde")

    if funding > FUNDING_THRESHOLD:
        active.append("Long pozisyonlar kalabalıklaşıyor")
    elif funding < -FUNDING_THRESHOLD:
        active.append("Short pozisyonlar kalabalıklaşıyor")

    return len(active), active


def label(score: int) -> str:
    return SCORE_LABELS.get(score, "güçlü")
