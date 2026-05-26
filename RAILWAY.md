# Railway Deployment Guide

## Overview
This guide explains how to deploy the Alpha Metric Telegram bot to Railway.

## Prerequisites
- GitHub account (repo already pushed to `rk7tdf4pw2-bit/alpha-metric`)
- Railway account (https://railway.app)
- Telegram Bot Token from @BotFather

## Step 1: Create Railway Project

1. Go to https://railway.app
2. Sign in with GitHub
3. Click "New Project" → "Deploy from GitHub repo"
4. Select `rk7tdf4pw2-bit/alpha-metric`

## Step 2: Configure Environment Variables

In Railway Dashboard:
1. Go to your project
2. Click "Variables" (or ⚙️ Settings)
3. Add these variables:

```
TELEGRAM_TOKEN=your_bot_token_from_botfather
```

## Step 3: Configure Service Type

The `Procfile` will automatically tell Railway:
```
worker: python bot.py
```

This means:
- Service type: `Worker` (not a Web service - bot doesn't need HTTP port)
- Command: `python bot.py`
- Python version: 3.11.9 (specified in `runtime.txt`)

## Step 4: Deploy

1. Click "Deploy" button in Railway Dashboard
2. Wait for build to complete
3. Check logs to verify bot started:
```
🤖 Alpha Metric Bot starting... (polling mode)
✓ Bot initialization complete - database ready, scheduler started
```

## Step 5: Monitor & Troubleshoot

### View Logs
- Railway Dashboard → Select service → "Logs" tab
- Shows real-time output from `python bot.py`

### Common Issues

**Token Error:**
```
❌ TELEGRAM_TOKEN not set!
```
→ Make sure `TELEGRAM_TOKEN` is set in Railway Variables

**Database Issues:**
```
bot.db is created in the working directory on Railway
```
→ This is normal; Railway keeps the file between restarts (as long as the service doesn't get recreated)

### Persistent Storage (required for intelligence loop)

The self-improving intelligence loop writes to `logs/` at runtime.
Without a persistent volume, all reasoning/outcome/calibration history
is lost on every deploy, disabling confidence calibration entirely.

**Step A — Add Volume in Railway Dashboard:**
1. Open your service in Railway Dashboard
2. Click "+" → "Volume"  (or Settings → Volumes → Add Volume)
3. Set **Mount Path** to `/app/logs`
4. Set **Size** to `1 GB` (sufficient for ~60,000 records)
5. Save and redeploy

**Step B — Verify it works:**
After deploy, run `/analyze BTC` in Telegram and check Railway logs for:
```
[ARCHIVE] BTCUSDT: kayıt eklendi balance=... confidence=...
```
Then redeploy again and check that the file still exists:
```
[OUTCOME] Başlangıç: N mevcut değerlendirme yüklendi
```

**Alternative — use a custom path:**
If you mount the volume at a different path (e.g. `/data`), set:
```
LOGS_DIR=/data/logs
```
in Railway Variables. No code change needed.

## Redeployment

To redeploy after code changes:
```bash
git push origin main
```
Railway will automatically rebuild and redeploy when it detects changes.

## Scaling & Monitoring

- Railway shows CPU/Memory usage in the dashboard
- Bot runs in polling mode (not webhook) which is compatible with Railway
- Check status page: https://railway.app/status

---

## File Structure (Production-Ready)

```
telegram_bot/
├── bot.py              # ✅ Main entry point with error handling
├── Procfile            # ✅ Tells Railway how to start bot
├── runtime.txt         # ✅ Python version specification
├── requirements.txt    # ✅ Pinned dependencies
├── .env.example        # ✅ Environment variables template
├── .env                # ⚠️ LOCAL ONLY - not in GitHub
├── .gitignore          # ✅ Protects .env
├── config/
│   └── settings.py     # ✅ Railway-compatible config loading
├── database/
│   └── db.py           # Creates bot.db automatically
├── handlers/           # Bot command handlers
├── services/           # Background tasks & API integrations
├── templates/          # Message templates & keyboards
└── utils/              # Logger & HTTP utilities
```

---

## What to Do Next

1. **Test Locally (Recommended)**
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   export TELEGRAM_TOKEN="your_token"
   python bot.py
   ```

2. **Push to Railway**
   - Make sure all changes are committed and pushed to GitHub
   - Railway will auto-deploy on `git push origin main`

3. **Monitor First 24 Hours**
   - Check Railway logs for any issues
   - Test bot commands: `/start`, `/price BTC`, etc.

---

## Security Notes

✅ **Already Configured:**
- `.env` is in `.gitignore` - secrets won't be uploaded to GitHub
- `TELEGRAM_TOKEN` should be set in Railway Variables, not in git

⚠️ **Before Production:**
- Never commit `.env` files
- Use Railway Variables for all secrets
- Rotate token if accidentally exposed

---

## Support

For Railway-specific issues:
- Railway Docs: https://docs.railway.app/
- For bot logic issues: Check `services/` and `handlers/` modules
