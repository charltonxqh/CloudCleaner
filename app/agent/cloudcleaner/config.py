"""Backend configuration. Reads environment variables with sane defaults.
Add settings here as new components need them.
"""

import os


class Settings:
    AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")

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
