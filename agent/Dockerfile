FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev --extra server

RUN uv pip install "mcp>=2,<3"

COPY . .

EXPOSE 8123
EXPOSE 8130

CMD ["uv", "run", "--no-dev", "--extra", "server", "python", "main.py"]