import os
from pathlib import Path

from dotenv import load_dotenv


# app/agent/cloudcleaner/config.py -> app/
PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(PROJECT_ROOT / ".env")


GROQ_API_KEY = os.getenv("GROQ_API_KEY")

GROQ_MODEL = os.getenv(
    "GROQ_MODEL",
    "openai/gpt-oss-20b",
)

AWS_REGION = os.getenv(
    "AWS_REGION",
    "us-east-1",
)
METRIC_WINDOW_DAYS = int(os.getenv("METRIC_WINDOW_DAYS", "7"))

AWS_ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL") or None

DRY_RUN = os.getenv("CLOUDCLEANER_DRY_RUN", "true").lower() not in ("false", "0", "no")

AI_ENABLED = os.getenv("CLOUDCLEANER_AI_ENABLED", "true").lower() not in ("false", "0", "no")

PROVIDER = os.getenv("CLOUDCLEANER_PROVIDER", "aws").lower()  # display only; see tools/provider.py
