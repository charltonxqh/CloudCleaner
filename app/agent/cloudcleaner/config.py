"""Backend configuration. Reads environment variables (via app/.env) with
sane defaults. Add settings here as new components need them.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

APP_DIR = Path(__file__).resolve().parents[2]
load_dotenv(APP_DIR / ".env")

# Top-level constants for simple `from cloudcleaner.config import X` imports.
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")


class Settings:
    AWS_REGION: str = AWS_REGION
    GROQ_API_KEY: str | None = GROQ_API_KEY
    GROQ_MODEL: str = GROQ_MODEL
    GITHUB_TOKEN: str | None = GITHUB_TOKEN

    # Safety / Actions / Evaluation settings
    DRY_RUN: bool = os.getenv("CLOUDCLEANER_DRY_RUN", "true").lower() == "true"
    VERIFY_MAX_ATTEMPTS: int = int(os.getenv("CLOUDCLEANER_VERIFY_MAX_ATTEMPTS", "5"))
    VERIFY_POLL_INTERVAL_SECONDS: float = float(
        os.getenv("CLOUDCLEANER_VERIFY_POLL_INTERVAL", "2")
    )
    ROLLBACK_MAX_RETRIES: int = int(os.getenv("CLOUDCLEANER_ROLLBACK_MAX_RETRIES", "2"))
    COST_APPROVAL_THRESHOLD_USD: float = float(
        os.getenv("CLOUDCLEANER_COST_THRESHOLD_USD", "50")
    )


settings = Settings()
