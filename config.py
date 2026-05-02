import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "sk-your-key")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
MODEL_VISION = "gpt-4o"
MODEL_TEXT = "gpt-4o-mini"

WECOM_WEBHOOK = os.getenv("WECOM_WEBHOOK", "")

TARGET_URLS = [
    "https://example.com/product/123",
    "https://example.com/product/456",
]

HISTORY_FILE = "history.json"
PRICE_DROP_ALERT_PERCENT = 0.15
SENTIMENT_SHIFT_THRESHOLD = 0.3