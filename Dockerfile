FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
COPY graders ./graders
COPY styles ./styles
COPY recipes ./recipes

# uv with the overrides file: pydantic-ai needs openai 3, which plain pip refuses because
# llama-index-llms-openai pins openai<3 (see scripts/uv-overrides.txt).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY scripts/uv-overrides.txt ./
RUN uv pip install --system --no-cache . --override uv-overrides.txt

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
