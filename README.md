# 🤖 Alpha Metric - Telegram Crypto Analytics Bot

[![GitHub](https://img.shields.io/badge/GitHub-rk7tdf4pw2--bit%2Falpha--metric-blue)](https://github.com/rk7tdf4pw2-bit/alpha-metric)
[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green)](#license)

A production-ready Telegram bot that provides real-time cryptocurrency market analysis, price alerts, RSI indicators, and intelligent signal scoring for informed trading decisions.

> ⚠️ **Disclaimer**: Alpha Metric provides market data and analysis tools only. It does **not** provide investment advice. All trading decisions are the user's responsibility.

---

## 🌟 Features

### 📊 Real-Time Market Data
- **Instant Price Lookup** → `/price BTC` returns current price in USDT
- **RSI Analysis** → `/rsi ETH` calculates 14-period RSI with interpretation
- **Funding Rate Monitoring** → Tracks perpetual future funding rates
- **Signal Scoring** → Combines RSI + funding data for composite market signals

### 🔔 Intelligent Alerts
- **Price Alerts** → Set "alert above/below" thresholds; automatic notifications
- **RSI Alerts** → Monitor overbought (>70) and oversold (<30) conditions
- **Funding Alerts** → Track extreme funding rates indicating position clustering
- **Cooldown System** → Rate-limited alerts prevent spam

### 📱 Portfolio Management
- **Watchlist** → `/addcoin BTC` add tokens to track
- **My Coins** → `/mycoins` view your personalized watchlist
- **Daily Pulse** → Scheduled summary of market changes

### 👤 User Management
- **Premium Tiers** → `/premium_on` enable premium features for users
- **Analytics Tracking** → Track user behavior and feature usage
- **Admin Controls** → Manage premium status, monitor bot activity

---

## 💬 Commands

| Command | Usage | Description |
|---------|-------|-------------|
| `/start` | `/start` | Initialize bot, view welcome message |
| `/price` | `/price BTC` | Get current price in USDT |
| `/rsi` | `/rsi ETH` | Calculate RSI (14-period) with analysis |
| `/addcoin` | `/addcoin SOL` | Add token to watchlist |
| `/mycoins` | `/mycoins` | View your watchlist |
| `/alert` | `/alert BTC above 50000` | Create price alert |
| `/premium_on` | `/premium_on <user_id>` | Grant premium status (admin) |
| `/premium_off` | `/premium_off <user_id>` | Revoke premium status (admin) |

---

## 🏗️ Architecture Overview

### System Design

```
┌─────────────────────────────────────────────────────────┐
│                  Telegram Bot (polling)                 │
│  ┌──────────────────────────────────────────────────┐   │
│  │         Command Handlers (telegram.ext)          │   │
│  │  ├─ start.py     │ price.py    │ watchlist.py   │   │
│  │  ├─ alert.py     │ rsi.py      │ admin.py       │   │
│  └──────────────────────────────────────────────────┘   │
└───────────┬────────────────────────────────────────────┘
            │
    ┌───────┼─────────┬─────────┬──────────┐
    │       │         │         │          │
    ▼       ▼         ▼         ▼          ▼
┌─────┐ ┌─────┐ ┌──────┐ ┌──────┐   ┌────────┐
│ DB  │ │API  │ │Tasks │ │Utils │   │Config  │
└─────┘ └─────┘ └──────┘ └──────┘   └────────┘
```

### Core Components

**1. Handlers** (`handlers/`)
- Parse user commands
- Validate arguments
- Call services for data
- Return formatted responses

**2. Services** (`services/`)
- **Market Data** → Bybit API integration for prices, RSI, funding
- **Scheduler** → Background job runner (60-second interval)
- **Tasks** → Automated checks (price alerts, RSI alerts, daily pulse)
- **Analytics** → User behavior tracking
- **Cooldown** → Rate limiting per user
- **Signal Score** → ML-ready composite signals

**3. Database** (`database/`)
- SQLite with async operations
- Tables: users, watchlists, alerts, analytics
- Auto-initialized on startup

**4. Templates** (`templates/`)
- Message formatting (alert templates, keyboards)
- Consistent bot response styling

**5. Utils** (`utils/`)
- HTTP client (httpx)
- Logger (structured logging)

---

## 📁 Folder Structure

```
telegram_bot/
├── bot.py                          # Main entry point
├── requirements.txt                # Python dependencies
├── Procfile                        # Railway deployment config
├── runtime.txt                     # Python version (3.11.9)
├── .env                            # Local environment variables ⚠️
├── .env.example                    # Template for Railway
├── .gitignore                      # Git ignore rules
├── README.md                       # This file
├── RAILWAY.md                      # Railway deployment guide
│
├── config/
│   ├── __init__.py
│   └── settings.py                 # ENV loading, TOKEN config
│
├── database/
│   ├── __init__.py
│   └── db.py                       # SQLite async operations
│
├── handlers/
│   ├── __init__.py
│   ├── start.py                    # /start command
│   ├── price.py                    # /price BTC command
│   ├── rsi.py                      # /rsi ETH command
│   ├── watchlist.py                # /addcoin, /mycoins
│   ├── alert.py                    # /alert BTC above 50000
│   ├── admin.py                    # /premium_on, /premium_off
│   └── btc.py                      # BTC-specific handlers
│
├── services/
│   ├── __init__.py
│   ├── market_data.py              # Bybit API integration
│   ├── rsi.py                      # RSI calculation
│   ├── funding.py                  # Funding rate fetching
│   ├── scheduler.py                # Background task runner
│   ├── signal_score.py             # Composite signal scoring
│   ├── analytics.py                # Usage tracking
│   ├── cooldown.py                 # Rate limiting
│   └── tasks/
│       ├── __init__.py
│       ├── price_alerts.py         # Check & notify price alerts
│       ├── rsi_alerts.py           # Check & notify RSI alerts
│       ├── funding_alerts.py       # Check & notify funding alerts
│       ├── signal_alerts.py        # Check signal score changes
│       └── daily_pulse.py          # Daily market summary
│
├── templates/
│   ├── __init__.py
│   ├── messages.py                 # Alert & message templates
│   └── keyboards.py                # Inline keyboards & buttons
│
└── utils/
    ├── __init__.py
    ├── http.py                     # HTTP client (httpx wrapper)
    └── logger.py                   # Logging configuration
```

---

## 🚀 Deployment

### Quick Start (Local Development)

```bash
# Clone repository
git clone https://github.com/rk7tdf4pw2-bit/alpha-metric.git
cd telegram_bot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # macOS/Linux
# or
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and add your TELEGRAM_TOKEN from @BotFather

# Run bot
python bot.py
```

### Railway Deployment

For detailed Railway deployment steps, see [RAILWAY.md](RAILWAY.md).

**Quick summary:**
1. Push code to GitHub (already done ✅)
2. Connect to Railway with GitHub account
3. Create new project from `rk7tdf4pw2-bit/alpha-metric`
4. Add `TELEGRAM_TOKEN` environment variable
5. Deploy (Railway reads `Procfile` automatically)

---

## 🔐 Environment Variables

### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `TELEGRAM_TOKEN` | Telegram Bot API token from @BotFather | `123456789:ABCdef-GHIjkl_MNOpqr-STUvwxYZ` |

### Optional (Future Use)

```bash
# Admin user ID for advanced features
ADMIN_ID=123456789

# Database URL (if migrating to PostgreSQL)
DATABASE_URL=postgresql://user:pass@host/db

# API rate limits
API_RATE_LIMIT=100

# Premium features
PREMIUM_ALERT_LIMIT=50
```

---

## 🔒 Security

### ✅ Protected
- ✓ `TELEGRAM_TOKEN` required (validates on startup)
- ✓ `.env` file in `.gitignore` (never exposed to GitHub)
- ✓ No hardcoded secrets in code
- ✓ Rate limiting prevents bot abuse
- ✓ Admin commands require authorization

### 🛡️ Best Practices
- Always use `TELEGRAM_TOKEN` from environment variables
- Rotate token if accidentally exposed: Message @BotFather
- Store sensitive data in Railway Variables dashboard, never in `.env`
- Disable admin commands if not needed
- Monitor logs for suspicious activity

### 📋 Compliance Notes
- Bot only provides **data and analysis** — not investment advice
- Users are responsible for trading decisions
- No personal financial information stored
- Analytics tracking is anonymous (user_id only)

---

## 🛣️ Roadmap

### Phase 1: Current (v1.0)
- [x] Price lookup
- [x] RSI analysis
- [x] Price/RSI alerts
- [x] Watchlist management
- [x] Funding rate monitoring
- [x] Signal scoring
- [x] Railway deployment ready

### Phase 2: Enhancements (v1.1-v1.2)
- [ ] Multiple timeframe analysis (1h, 4h, 1d)
- [ ] Moving averages (MA200, MA50)
- [ ] Stochastic RSI
- [ ] MACD analysis
- [ ] Volume profile
- [ ] Custom alert conditions (e.g., `BTC > 50k AND RSI > 70`)
- [ ] Notification channels (Discord, Slack)
- [ ] Database export (CSV reports)

### Phase 3: Advanced Features (v2.0+)
- [ ] Portfolio tracking
- [ ] P&L calculator
- [ ] Trading journal
- [ ] Backtesting engine
- [ ] Web dashboard
- [ ] Mobile app

---

## 🤖 AI/Agent-Oriented Architecture (Future)

### Vision: Intelligent Crypto Agent System

The bot is designed to evolve into an **agent-based system** capable of autonomous market analysis and decision recommendations.

#### Current Foundation
```
Command Handler → Service → Data → Response
  (Reactive)
```

#### Future Agent Architecture
```
┌──────────────────────────────────────────────┐
│         Multi-Agent System                   │
├──────────────────────────────────────────────┤
│                                              │
│  ┌─────────────────────────────────────┐    │
│  │  Market Analysis Agent              │    │
│  │  - Continuous market monitoring     │    │
│  │  - Technical pattern recognition    │    │
│  │  - Anomaly detection                │    │
│  └─────────────────────────────────────┘    │
│                                              │
│  ┌─────────────────────────────────────┐    │
│  │  Signal Generation Agent            │    │
│  │  - Multi-indicator scoring          │    │
│  │  - Weighted signal aggregation      │    │
│  │  - Confidence scoring               │    │
│  └─────────────────────────────────────┘    │
│                                              │
│  ┌─────────────────────────────────────┐    │
│  │  Alert & Decision Agent             │    │
│  │  - Smart notification logic         │    │
│  │  - Context-aware messaging          │    │
│  │  - Risk assessment                  │    │
│  └─────────────────────────────────────┘    │
│                                              │
│  ┌─────────────────────────────────────┐    │
│  │  Learning Agent                     │    │
│  │  - Historical performance tracking  │    │
│  │  - Pattern learning                 │    │
│  │  - Model improvement                │    │
│  └─────────────────────────────────────┘    │
│                                              │
└──────────────────────────────────────────────┘
```

#### Key Architectural Changes for Agents

**1. Signal Service Expansion**
```python
# Current: Simple scoring
signal_score.compute(rsi, funding)

# Future: Multi-agent analysis
class MarketAnalysisAgent:
    async def analyze(symbol) -> MarketSignal:
        - Technical patterns (MA, MACD, Bollinger)
        - On-chain metrics
        - Funding patterns
        - Volume anomalies
        - Sentiment analysis
        → Returns: confidence_score, signal_strength
```

**2. State Management**
```python
# Agent memory & state
class AgentMemory:
    - Historical patterns
    - User preferences
    - Performance metrics
    - Context awareness
    
# Persistent storage
database/
├── agent_states.db
├── pattern_history.db
└── performance_metrics.db
```

**3. Decision Making**
```python
# Autonomous recommendation logic
class DecisionAgent:
    async def recommend(market_state) -> Recommendation:
        - Risk assessment
        - Opportunity scoring
        - Timing analysis
        - Confidence intervals
        → Returns: BUY/SELL/HOLD with confidence%
```

**4. Learning Loop**
```python
# Feedback & improvement
class LearningAgent:
    async def track_performance(recommendation, actual_price):
        - Store outcome
        - Calculate accuracy
        - Adjust future signals
        - Model improvement
```

#### Potential Integration Points

**LLM Integration (GPT-4, Claude, Grok)**
```python
# Natural language analysis
llm_agent = LanguageAgent()
analysis = await llm_agent.analyze(
    market_data=latest_data,
    query="What's the best setup for BTC this week?"
)
# Returns: Natural language analysis + recommendations
```

**On-Chain Analysis**
```python
# Blockchain metrics
blockchain_agent = BlockchainAgent()
metrics = await blockchain_agent.analyze(
    whale_wallets_movement,
    exchange_inflows,
    transaction_volume,
    contract_interactions
)
```

**Sentiment Analysis**
```python
# Social & news sentiment
sentiment_agent = SentimentAgent()
sentiment = await sentiment_agent.analyze(
    twitter_mentions=get_twitter(symbol),
    reddit_posts=get_reddit(symbol),
    news_articles=get_news(symbol)
)
```

#### Example: Future Agent Message
```
🤖 Alpha Metric Analysis for BTC
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Current: $65,234

Technical Score: 7.2/10 🟡
├─ RSI: 52 (Neutral)
├─ MA200: Above (Bullish)
├─ MACD: Positive (Bullish)
└─ Volume: Declining (Bearish)

On-Chain Score: 6.8/10 🟡
├─ Whale Accumulation: +12%
├─ Exchange Outflows: High
└─ Open Interest: Rising

Sentiment: 7.5/10 🟢
├─ Twitter: 68% Positive
├─ Reddit: 72% Bullish
└─ News: Mixed

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Composite Signal: MODERATE BUY
Confidence: 71%
Risk Level: Medium
Suggested Entry: $64,800-65,000

🔔 Set alert at $65,500 to lock profits?
```

---

## 🛠️ Development

### Project Structure Philosophy
- **Separation of Concerns**: Handlers, Services, Database are independent
- **Async First**: All I/O operations are async (database, HTTP, messaging)
- **Modular Services**: Easy to add new market indicators
- **Testable Design**: Services can be tested independently
- **Scalable**: Can be extended to multi-region deployment

### Adding a New Feature

Example: Add MACD analysis

```python
# 1. Add service
services/macd.py
async def get_macd(symbol: str) -> dict:
    # Fetch OHLC data
    # Calculate MACD, Signal Line, Histogram
    # Return results

# 2. Add handler
handlers/macd.py
async def macd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Parse args
    # Call service
    # Format response

# 3. Register in bot.py
app.add_handler(CommandHandler("macd", macd))

# 4. Create task if needed
services/tasks/macd_alerts.py
async def run(app):
    # Check MACD crossovers
    # Send alerts
```

### Testing

```bash
# Run locally
export TELEGRAM_TOKEN="test_token"
python bot.py

# Monitor logs
tail -f logs/bot.log

# Check database
sqlite3 bot.db ".tables"
```

---

## 📊 Data Sources

| Data | Source | Rate Limit | Reliability |
|------|--------|-----------|-------------|
| Prices | Bybit API | 10 req/sec | ✅ Enterprise |
| RSI | TA-Lib | Local calculation | ✅ Deterministic |
| Funding Rates | Bybit API | 10 req/sec | ✅ Official |
| Volume | Bybit API | 10 req/sec | ✅ Official |

---

## 📈 Performance & Limits

| Metric | Current | Scalable To |
|--------|---------|------------|
| Commands/second | 10 | 100+ |
| Concurrent users | 1,000 | 10,000+ |
| Alerts active | 100 | 10,000+ |
| API calls/minute | 600 | 5,000+ |
| Database | SQLite | PostgreSQL |
| Deployment | Railway | Kubernetes |

---

## 🤝 Contributing

Contributions welcome! Areas for improvement:

1. **Additional Indicators** - Add MACD, Bollinger Bands, Ichimoku
2. **More Data Sources** - Binance, Kraken, Coinbase APIs
3. **Performance** - Database optimization, caching layer
4. **Testing** - Unit tests, integration tests
5. **Documentation** - Developer guides, API docs
6. **UI** - Web dashboard, inline keyboards improvements
7. **Agent Features** - Implement multi-agent architecture ideas

---

## 📝 License

MIT License - See LICENSE file for details

---

## 📞 Support & Contact

- **Issues**: Report bugs on GitHub Issues
- **Telegram**: Contact via bot `/start` → feedback menu (future)
- **Email**: [Add contact if desired]

---

## ⭐ Acknowledgments

- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) - Telegram Bot API wrapper
- [Bybit API](https://bybit-exchange.github.io/) - Crypto market data
- [Railway](https://railway.app) - Infrastructure & deployment
- Contributors & users providing feedback

---

**Alpha Metric** — *Market Intelligence for Informed Traders* 📊

Last Updated: May 22, 2026
