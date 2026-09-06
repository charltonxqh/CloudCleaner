"""Kept so `uv run main.py` still works from a checkout.

The app itself lives in cloudcleaner/server.py so that an installed copy can
serve it too.
"""

from cloudcleaner.server import app, main

__all__ = ["app", "main"]

if __name__ == "__main__":
    main()
