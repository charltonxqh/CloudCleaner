FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev --extra server

COPY . .

EXPOSE 8123

CMD ["uv", "run", "--no-dev", "--extra", "server", "python", "main.py"]