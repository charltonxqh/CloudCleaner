"""Dev entrypoint. `npm run dev` runs this file.

The application itself lives in cloudcleaner/server.py so that an installed
copy serves the same API through `cloudcleaner serve`. Keeping the app in one
place is the point: these two had drifted into separate copies, and only this
one had the monitoring endpoints.
"""

import os

import uvicorn

from cloudcleaner.server import app  # noqa: F401  (re-exported for `uvicorn main:app`)


def main():
    uvicorn.run(
        "cloudcleaner.server:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8123")),
        reload=True,
    )


if __name__ == "__main__":
    main()
