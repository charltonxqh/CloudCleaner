import os
from pathlib import Path

from dotenv import load_dotenv


# app/agent/cloudcleaner/config.py
APP_DIR = Path(__file__).resolve().parents[2]

load_dotenv(APP_DIR / ".env")


GROQ_API_KEY = os.getenv("GROQ_API_KEY")

GROQ_MODEL = os.getenv(
    "GROQ_MODEL",
    "openai/gpt-oss-20b",
)

AWS_REGION = os.getenv(
    "AWS_REGION",
    "us-east-1",
)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")