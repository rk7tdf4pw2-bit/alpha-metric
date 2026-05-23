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

CMC_API_KEY = os.getenv("CMC_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Reasoning layer controls — tune via Railway environment variables
REASONING_ENABLED = os.getenv("REASONING_ENABLED", "true").lower() == "true"
MAX_REASONING_TOKENS = int(os.getenv("MAX_REASONING_TOKENS", "700"))
REASONING_TIMEOUT = int(os.getenv("REASONING_TIMEOUT", "40"))  # seconds, Claude API call only

# Starter watchlist configuration for onboarding
STARTER_WATCHLIST = ["BTC", "ETH", "SOL"]

