import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / ".env"

# Load .env if it exists (local development)
# Railway will use environment variables directly
if env_path.exists():
    load_dotenv(dotenv_path=env_path, override=True)

TOKEN = os.getenv("TELEGRAM_TOKEN")

# Starter watchlist configuration for onboarding
STARTER_WATCHLIST = ["BTC", "ETH", "SOL"]

