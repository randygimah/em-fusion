# an official lightweight Python runtime as the parent image
FROM python:3.13.15-alpine AS base

# uv resolves and installs from pyproject.toml + uv.lock. Pinned by digest-backed
# tag so the installer itself is as reproducible as what it installs.
COPY --from=ghcr.io/astral-sh/uv:0.9.7-alpine /usr/local/bin/uv /usr/local/bin/uv

# Working directory
WORKDIR /app

# Environment variables to optimise python behaviour
# PYTHONDONTWRITEBYTECODE=1 prevents python from writing .pyc cache files to disk, saving space
# PYTHONUNBUFFERED ensures that console logs are printed instantly instead of buffering, making debugging easier
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install into the image's system interpreter rather than /app/.venv. Compose
# bind-mounts ./backend over /app in development, which would otherwise hide a
# virtualenv living there and break every command in the container.
ENV UV_PROJECT_ENVIRONMENT=/usr/local
ENV UV_LINK_MODE=copy

# Copy dependency manifests first: this layer is invalidated only when
# dependencies change, so editing source does not reinstall the world.
COPY pyproject.toml uv.lock ./

# Install runtime dependencies exactly as locked
RUN uv sync --locked --no-install-project --no-dev

# Copy rest of application code into container
COPY . .

# Expose the port that uvicorn run on
EXPOSE 8000

# ==========================================
#  Dev image — adds pytest/mypy/black/flake8
# ==========================================
# Compose builds this target so `make test` and `make lint` run the dev
# toolchain in the same container that serves the app.
FROM base AS dev

RUN uv sync --locked --no-install-project

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ==========================================
#  Runtime image — locked dependencies only
# ==========================================
FROM base AS runtime

# Command to run the app using uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
