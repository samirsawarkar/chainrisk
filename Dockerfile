FROM python:3.11

# Node.js (>=18) and npm
RUN apt-get update \
  && apt-get install -y --no-install-recommends nodejs npm \
  && rm -rf /var/lib/apt/lists/*

# uv from official image
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /uvx /bin/

WORKDIR /app

# Dependency manifests first (layer cache)
COPY package.json package-lock.json ./
COPY frontend/package.json frontend/package-lock.json ./frontend/
COPY backend/pyproject.toml backend/uv.lock ./backend/

# Install Node and Python deps
RUN npm ci \
  && npm ci --prefix frontend \
  && cd backend && uv sync --frozen

# Application source
COPY . .

EXPOSE 3000 5001

# Dev: frontend + backend
CMD ["npm", "run", "dev"]