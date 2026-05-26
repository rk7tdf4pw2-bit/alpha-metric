"""
/analyze SYMBOL handler — human-triggered full reasoning pipeline.

Pipeline (sequential, observable):
  1. get_asset_context    → Binance kline data + classification
  2. get_market_overview  → CoinMarketCap macro context (optional)
  3. analyze_context      → contradiction engine (deterministic)
  4. build_analysis       → unified AnalysisSchema
  5. generate_reasoning   → Claude AI interpretation (with fallback)

Design notes:
  - Per-user cooldown prevents accidental spam (ANALYZE_COOLDOWN_SECONDS)
  - asyncio.wait_for with 60s pipeline timeout prevents Telegram from hanging
  - Immediate "processing" message edited on completion — avoids silent wait
  - Markdown stripped from Claude output to avoid Telegram parse errors
  - This command exists to validate reasoning quality before any automation
"""

import asyncio
import time
import traceback

from telegram import Update
from telegram.ext import ContextTypes

from services.intelligence.asset_context import get_asset_context
from services.intelligence.contradiction_engine import analyze_context
from services.intelligence.analysis_schema import build_analysis
from services.intelligence.market_overview import get_market_overview
from services.intelligence.reasoning import generate_reasoning
from services.intelligence.rule_weight_engine import load_active_weights
from templates.analysis_format import format_analysis
from utils import normalize_symbol
from utils.logger import logger

PIPELINE_TIMEOUT = 60       # seconds — covers Binance + Claude round-trips
ANALYZE_COOLDOWN_SECONDS = 30   # per-user minimum gap between /analyze calls

# Simple in-memory rate limiter: user_id → last_call unix timestamp
_last_analyze: dict[int, float] = {}


# ── Pipeline ───────────────────────────────────────────────────────────────────

async def _run_pipeline(binance_symbol: str):
    """Run the full intelligence pipeline. Raises on unrecoverable errors."""
    # Step 1: Asset context (Binance klines)
    logger.info(f"[ANALYZE] {binance_symbol}: [1/5] Binance kline verisi alınıyor")
    asset_ctx = await get_asset_context(binance_symbol)
    if asset_ctx is None:
        raise ValueError(f"Binance verisi alınamadı: {binance_symbol}")
    logger.info(
        f"[ANALYZE] {binance_symbol}: [1/5] OK — "
        f"trend_1h={asset_ctx['short_term_trend']} "
        f"rsi={asset_ctx['rsi_state']} "
        f"momentum={asset_ctx['momentum']}"
    )

    # Step 2: Market overview (CoinMarketCap — optional, never blocks)
    logger.info(f"[ANALYZE] {binance_symbol}: [2/5] Market overview alınıyor")
    market_overview = await get_market_overview()
    logger.info(f"[ANALYZE] {binance_symbol}: [2/5] OK — overview={'var' if market_overview else 'yok'}")

    # Step 3: Contradiction engine (weighted when historical data available)
    logger.info(f"[ANALYZE] {binance_symbol}: [3/5] Contradiction engine çalıştırılıyor")
    weights = load_active_weights()
    contradiction = analyze_context(asset_ctx, weights=weights)
    logger.info(
        f"[ANALYZE] {binance_symbol}: [3/5] OK — "
        f"balance={contradiction['overall_context_balance']} "
        f"supporting={len(contradiction['supporting_factors'])} "
        f"contradictions={len(contradiction['contradictions'])}"
    )

    # Step 4: Analysis schema (assembles all layers)
    logger.info(f"[ANALYZE] {binance_symbol}: [4/5] Analysis schema oluşturuluyor")
    schema = build_analysis(asset_ctx, contradiction, market_overview)
    logger.info(f"[ANALYZE] {binance_symbol}: [4/5] OK — schema hazır")

    # Step 5: AI reasoning (Claude API — with safe fallback)
    logger.info(f"[ANALYZE] {binance_symbol}: [5/5] AI reasoning başlatılıyor")
    reasoning_out = await generate_reasoning(schema)
    logger.info(
        f"[ANALYZE] {binance_symbol}: [5/5] OK — "
        f"fallback={reasoning_out['fallback_used']} "
        f"confidence={reasoning_out['confidence']} "
        f"tokens={reasoning_out['prompt_tokens']}+{reasoning_out['completion_tokens']} "
        f"ms={reasoning_out['reasoning_ms']}"
    )

    return schema, reasoning_out


# ── Handler ────────────────────────────────────────────────────────────────────

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"[ANALYZE] command received — args={context.args} user={update.effective_user and update.effective_user.id}")
    try:
        if not context.args:
            await update.message.reply_text(
                "Kullanım: /analyze SEMBOL\n\nÖrnekler:\n/analyze BTCUSDT\n/analyze ETH"
            )
            return

        raw_symbol = context.args[0]
        logger.info(f"[ANALYZE] sembol ayrıştırılıyor: raw={raw_symbol!r}")
        binance_symbol = normalize_symbol(raw_symbol)

        if binance_symbol is None:
            await update.message.reply_text(
                f"'{raw_symbol}' geçerli bir sembol değil. Örnek: /analyze BTC"
            )
            return

        logger.info(f"[ANALYZE] sembol OK: {binance_symbol}")

        # Per-user rate limit — checked BEFORE sending "processing" message
        user_id = update.effective_user.id
        now = time.time()
        last_call = _last_analyze.get(user_id, 0.0)
        elapsed_since_last = now - last_call

        if elapsed_since_last < ANALYZE_COOLDOWN_SECONDS:
            remaining = int(ANALYZE_COOLDOWN_SECONDS - elapsed_since_last)
            logger.info(
                f"[ANALYZE] rate limit: user={user_id} symbol={binance_symbol} "
                f"kalan={remaining}s"
            )
            await update.message.reply_text(
                f"⏳ Lütfen {remaining} saniye bekleyin. "
                f"/analyze komutu en sık {ANALYZE_COOLDOWN_SECONDS}s'de bir kullanılabilir."
            )
            return

        _last_analyze[user_id] = now

        # Immediate feedback — prevents silent wait during API calls
        logger.info(f"[ANALYZE] {binance_symbol}: processing mesajı gönderiliyor")
        processing_msg = await update.message.reply_text(
            f"⏳ {binance_symbol} analiz ediliyor..."
        )

    except Exception as e:
        logger.error(
            f"[ANALYZE] handler giriş hatası — {type(e).__name__}: {e}\n"
            f"{traceback.format_exc()}"
        )
        try:
            await update.message.reply_text("Analiz geçici olarak başarısız oldu.")
        except Exception:
            pass
        return

    try:
        logger.info(f"[ANALYZE] {binance_symbol}: pipeline başlatıldı (timeout={PIPELINE_TIMEOUT}s)")

        schema, reasoning_out = await asyncio.wait_for(
            _run_pipeline(binance_symbol),
            timeout=PIPELINE_TIMEOUT,
        )

        logger.info(f"[ANALYZE] {binance_symbol}: formatter çalıştırılıyor")
        output = format_analysis(schema, reasoning_out)
        logger.info(f"[ANALYZE] {binance_symbol}: Telegram mesajı gönderiliyor (chars={len(output)})")
        await processing_msg.edit_text(output)
        logger.info(f"[ANALYZE] {binance_symbol}: tamamlandı")

    except asyncio.TimeoutError:
        logger.warning(
            f"[ANALYZE] {binance_symbol}: TIMEOUT — pipeline {PIPELINE_TIMEOUT}s limitini aştı\n"
            f"{traceback.format_exc()}"
        )
        await processing_msg.edit_text(
            f"⏱ {binance_symbol} analizi zaman aşımına uğradı ({PIPELINE_TIMEOUT}s).\n"
            "Lütfen biraz bekleyip tekrar deneyin."
        )

    except ValueError as e:
        logger.warning(
            f"[ANALYZE] {binance_symbol}: ValueError — {e}\n"
            f"{traceback.format_exc()}"
        )
        await processing_msg.edit_text(
            f"❌ {binance_symbol} için veri alınamadı.\n"
            "Sembolü kontrol edin veya biraz sonra tekrar deneyin."
        )

    except BaseException as e:
        logger.error(
            f"[ANALYZE] {binance_symbol}: HATA — {type(e).__name__}: {e}\n"
            f"{traceback.format_exc()}"
        )
        try:
            await processing_msg.edit_text(
                f"Analiz geçici olarak başarısız oldu. Lütfen daha sonra tekrar deneyin."
            )
        except Exception:
            pass
        if isinstance(e, (KeyboardInterrupt, SystemExit)):
            raise
