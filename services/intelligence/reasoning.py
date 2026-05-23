"""
Reasoning — Claude API reasoning layer for Alpha Metric.

Input : AnalysisSchema (from analysis_schema.py)
Output: ReasoningOutput — structured AI interpretation, confidence, timing, token usage

Design constraints:
  - Reads ONLY from AnalysisSchema — no external API calls here
  - System prompt enforces: uncertainty awareness, grounded reasoning, no BUY/SELL
  - Safe fallback when Claude API is unavailable
  - Prompt caching on static system prompt (reduces token cost on repeated calls)
  - Structured logging: timing, token usage, failures
"""

import asyncio
import re
import time
from datetime import datetime, timezone
from typing import TypedDict

from anthropic import AsyncAnthropic, APIError, APIConnectionError, APITimeoutError

from config.settings import (
    ANTHROPIC_API_KEY,
    REASONING_ENABLED,
    MAX_REASONING_TOKENS,
    REASONING_TIMEOUT,
)
from services.intelligence.analysis_schema import AnalysisSchema
from services.intelligence.calibration_engine import (
    apply_confidence_cap,
    get_active_hints,
    inject_into_prompt,
    load_active_calibration,
)
from services.intelligence.reasoning_archive import build_record, write_reasoning_record
from services.intelligence.reasoning_validator import validate_reasoning
from utils.logger import logger


# ── Output schema ──────────────────────────────────────────────────────────────

class ReasoningOutput(TypedDict):
    symbol: str
    text: str               # full Claude response, ready for display
    confidence: str         # Düşük / Orta / Yüksek (extracted from response)
    model_used: str
    prompt_tokens: int
    completion_tokens: int
    reasoning_ms: int
    generated_at_iso: str
    fallback_used: bool


# ── Constants ──────────────────────────────────────────────────────────────────

_MODEL = "claude-opus-4-7"

# System prompt is static — cached by Anthropic to reduce cost on repeated calls
_SYSTEM_PROMPT = """Sen Alpha Metric'in yapay zeka destekli piyasa yorumlama katmanısın.

Görevin: Sana verilen yapılandırılmış piyasa bağlamını (kanıtlar, sinyaller, çelişkiler, riskler) yorumlayarak açıklanabilir, dürüst ve ölçülü bir analiz üretmek.

Kesin kurallar — bunları HİÇBİR KOŞULDA ihlal etme:
1. ASLA "al", "sat", "long", "short", "yatırım yap", "gir", "çık" gibi işlem tavsiyesi verme.
2. Sana verilmeyen veri hakkında tahminde bulunma — sadece şema içindeki bilgiye dayan.
3. Belirsizliği gizleme. Sinyaller çelişkili veya zayıfsa bunu açıkça belirt.
4. Kesinlik ifadesi kullanma ("kesinlikle yükselir", "mutlaka düşer" gibi). Piyasalar öngörülemez.
5. Her yorumun hangi kanıta dayandığını net göster.

Çıktı formatı — her bölümü sırayla yaz:
**Kanıtlar:** Şemadaki ham verileri kısaca özetle (sayıları tekrarlama, anlam çıkar).
**Bağlam:** Mevcut piyasa durumunu sınıflandır (trend, momentum, hacim, volatilite).
**Yorum:** Sinyaller birlikte ne söylüyor? Destekleyen ve zayıflatan faktörleri değerlendir.
**Güven:** Düşük / Orta / Yüksek — tek kelime, ardından tek cümleyle gerekçe.
**Riskler:** En önemli 1-2 riski kısa ve net yaz.

Dil: Türkçe. Ölçülü, teknik ama anlaşılır. Gereksiz dolgu cümle kullanma."""


# ── Module-level client (lazy init) ───────────────────────────────────────────

_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic | None:
    global _client
    if _client is not None:
        return _client
    if not ANTHROPIC_API_KEY:
        logger.warning("[REASONING] ANTHROPIC_API_KEY tanımlı değil, reasoning atlandı")
        return None
    _client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    return _client


# ── Prompt builder ─────────────────────────────────────────────────────────────

def _format_prompt(schema: AnalysisSchema) -> str:
    """Format all schema sections into a structured user message for Claude."""
    sym = schema["metadata"]["symbol"]
    lines: list[str] = [f"Sembol: {sym}", ""]

    lines.append("=== KANIT KATMANI (Ham Göstergeler) ===")
    for item in schema["evidence"]:
        lines.append(f"• {item}")

    ctx = schema["context"]
    lines.append("")
    lines.append("=== BAĞLAM KATMANI (Sınıflandırılmış Durumlar) ===")
    lines.append(f"• Kısa vadeli trend (1s SMA20): {ctx['short_term_trend']}")
    lines.append(f"• Üst zaman dilimi trendi (4s SMA20): {ctx['higher_tf_trend']}")
    lines.append(f"• Volatilite rejimi: {ctx['volatility_regime']}")
    lines.append(f"• Hacim durumu: {ctx['volume_condition']}")
    lines.append(f"• RSI durumu: {ctx['rsi_state']}")
    lines.append(f"• Momentum: {ctx['momentum']}")

    if schema["supporting_factors"]:
        lines.append("")
        lines.append("=== DESTEKLEYEN FAKTÖRLER ===")
        for item in schema["supporting_factors"]:
            lines.append(f"• {item}")

    if schema["weakening_factors"]:
        lines.append("")
        lines.append("=== ZAYIFLATAN FAKTÖRLER ===")
        for item in schema["weakening_factors"]:
            lines.append(f"• {item}")

    if schema["contradictions"]:
        lines.append("")
        lines.append("=== ÇELİŞKİLER ===")
        for item in schema["contradictions"]:
            lines.append(f"• {item}")

    lines.append("")
    lines.append(f"=== GENEL BAĞLAM DENGESİ: {schema['overall_context_balance'].upper()} ===")

    if schema["risks"]:
        lines.append("")
        lines.append("=== RİSKLER ===")
        for item in schema["risks"]:
            lines.append(f"• {item}")

    overview = schema.get("market_overview")
    if overview is not None:
        lines.append("")
        lines.append("=== MAKRO BAĞLAM (CoinMarketCap) ===")
        mcap_t = overview["total_market_cap_usd"] / 1e12
        vol_b = overview["total_volume_24h_usd"] / 1e9
        lines.append(f"• BTC dominance: {overview['btc_dominance']:.1f}%")
        lines.append(f"• Toplam piyasa değeri: ${mcap_t:.2f}T")
        lines.append(f"• 24s global hacim: ${vol_b:.1f}B")

    lines.append("")
    lines.append("Yukarıdaki yapılandırılmış bağlamı analiz et ve kurallara uygun yorumunu üret.")
    return "\n".join(lines)


# ── Confidence extractor ───────────────────────────────────────────────────────

_CONFIDENCE_RE = re.compile(
    r"\*\*Güven:\*\*\s*(Düşük|Orta|Yüksek)", re.IGNORECASE
)


def _extract_confidence(text: str) -> str:
    match = _CONFIDENCE_RE.search(text)
    if match:
        raw = match.group(1).capitalize()
        # Normalize casing
        mapping = {"Düşük": "Düşük", "Orta": "Orta", "Yüksek": "Yüksek"}
        return mapping.get(raw, "Orta")
    return "Orta"


# ── Fallback ───────────────────────────────────────────────────────────────────

def _build_fallback(schema: AnalysisSchema) -> ReasoningOutput:
    """Return a deterministic fallback when Claude API is unavailable."""
    sym = schema["metadata"]["symbol"]
    bal = schema["overall_context_balance"]
    ctx = schema["context"]

    confidence_map = {
        "aligned": "Yüksek",
        "mixed": "Orta",
        "conflicted": "Düşük",
        "weak": "Düşük",
    }
    confidence = confidence_map.get(bal, "Orta")

    text_lines = [
        f"**Kanıtlar:** {sym} için {len(schema['evidence'])} gösterge mevcut.",
        f"**Bağlam:** Kısa vade {ctx['short_term_trend']}, üst dilim {ctx['higher_tf_trend']}, "
        f"RSI {ctx['rsi_state']}, momentum {ctx['momentum']}.",
        f"**Yorum:** Sinyal dengesi '{bal}' olarak sınıflandırıldı. "
        "AI yorumlama katmanına şu an ulaşılamıyor; deterministik özet gösterildi.",
        f"**Güven:** {confidence} — AI katmanı devre dışı.",
    ]
    if schema["risks"]:
        text_lines.append("**Riskler:** " + " | ".join(schema["risks"][:2]))

    return ReasoningOutput(
        symbol=sym,
        text="\n".join(text_lines),
        confidence=confidence,
        model_used="fallback",
        prompt_tokens=0,
        completion_tokens=0,
        reasoning_ms=0,
        generated_at_iso=datetime.now(tz=timezone.utc).isoformat(),
        fallback_used=True,
    )


# ── Public API ─────────────────────────────────────────────────────────────────

async def generate_reasoning(schema: AnalysisSchema) -> ReasoningOutput:
    """
    Send AnalysisSchema to Claude and return a structured ReasoningOutput.
    Falls back to deterministic summary if the API is unavailable or disabled.
    """
    sym = schema["metadata"]["symbol"]

    # Safety gate: reasoning can be disabled via env var without code changes
    if not REASONING_ENABLED:
        logger.warning(f"[REASONING] {sym}: REASONING_ENABLED=false — fallback kullanılıyor")
        return _build_fallback(schema)

    client = _get_client()
    if client is None:
        # Warning already logged inside _get_client()
        return _build_fallback(schema)

    user_prompt = _format_prompt(schema)

    # Kalibrasyon ipuçlarını prompt'a enjekte et (concern/caution seviyesindekiler)
    calibration = load_active_calibration()
    active_hints = get_active_hints(dict(schema), calibration)
    if active_hints:
        user_prompt = inject_into_prompt(user_prompt, active_hints)
        logger.info(f"[REASONING] {sym}: {len(active_hints)} kalibrasyon ipucu enjekte edildi")

    prompt_chars = len(user_prompt)
    t0 = time.time()

    logger.info(
        f"[REASONING] {sym}: API çağrısı başlatılıyor "
        f"model={_MODEL} max_tokens={MAX_REASONING_TOKENS} "
        f"timeout={REASONING_TIMEOUT}s prompt_chars={prompt_chars}"
    )

    try:
        response = await asyncio.wait_for(
            client.messages.create(
                model=_MODEL,
                max_tokens=MAX_REASONING_TOKENS,
                thinking={"type": "adaptive"},
                system=[
                    {
                        "type": "text",
                        "text": _SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_prompt}],
            ),
            timeout=REASONING_TIMEOUT,
        )

        elapsed_ms = int((time.time() - t0) * 1000)

        # Extract text from response (skip thinking blocks)
        text = ""
        for block in response.content:
            if block.type == "text":
                text = block.text
                break

        usage = response.usage
        prompt_tokens = usage.input_tokens
        completion_tokens = usage.output_tokens
        confidence = _extract_confidence(text)

        # Kalibrasyon güven tavanı — concern seviyesinde kural varsa uygula
        confidence, cap_label = apply_confidence_cap(confidence, active_hints)
        if cap_label:
            logger.info(
                f"[REASONING] {sym}: güven tavanı uygulandı → {confidence} "
                f"(kaynak: {cap_label})"
            )

        # Quality validation — deterministic guardrail layer
        validation = validate_reasoning(text, symbol=sym)

        if validation["rejected"]:
            logger.warning(
                f"[REASONING] {sym}: KALİTE REDDİ — {validation['rejection_reason']} "
                f"chars={validation['char_count']} ms={elapsed_ms} → fallback aktif"
            )
            return _build_fallback(schema)

        for w in validation["warnings"]:
            logger.warning(f"[REASONING] {sym}: kalite uyarısı — {w}")

        logger.info(
            f"[REASONING] {sym}: OK "
            f"model={_MODEL} confidence={confidence} "
            f"prompt_tokens={prompt_tokens} completion_tokens={completion_tokens} "
            f"total_tokens={prompt_tokens + completion_tokens} "
            f"chars={validation['char_count']} warnings={len(validation['warnings'])} ms={elapsed_ms}"
        )

        # Archive — non-blocking; never raises to caller
        write_reasoning_record(build_record(
            symbol=sym,
            schema=dict(schema),
            reasoning_text=text,
            confidence=confidence,
            model_used=_MODEL,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            reasoning_ms=elapsed_ms,
            validator_warnings=validation["warnings"],
            validator_char_count=validation["char_count"],
            fallback_used=False,
        ))

        return ReasoningOutput(
            symbol=sym,
            text=text,
            confidence=confidence,
            model_used=_MODEL,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            reasoning_ms=elapsed_ms,
            generated_at_iso=datetime.now(tz=timezone.utc).isoformat(),
            fallback_used=False,
        )

    except asyncio.TimeoutError:
        elapsed_ms = int((time.time() - t0) * 1000)
        logger.warning(
            f"[REASONING] {sym}: TIMEOUT — Claude API {REASONING_TIMEOUT}s limitini aştı "
            f"ms={elapsed_ms} → fallback aktif"
        )
        return _build_fallback(schema)

    except (APIConnectionError, APITimeoutError) as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        logger.warning(
            f"[REASONING] {sym}: bağlantı hatası ({type(e).__name__}) "
            f"ms={elapsed_ms} → fallback aktif"
        )
        return _build_fallback(schema)

    except APIError as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        logger.error(
            f"[REASONING] {sym}: API hatası status={e.status_code} "
            f"ms={elapsed_ms} → fallback aktif"
        )
        return _build_fallback(schema)

    except Exception as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        logger.error(
            f"[REASONING] {sym}: beklenmeyen hata {type(e).__name__}: {e} "
            f"ms={elapsed_ms} → fallback aktif"
        )
        return _build_fallback(schema)
