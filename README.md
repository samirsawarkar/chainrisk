# ChainRisk

English-first multi-agent simulation platform for scenario forecasting.

Repository: [samirsawarkar/chainrisk](https://github.com/samirsawarkar/chainrisk)

## Overview

ChainRisk builds a simulation world from source documents and a natural-language brief. It creates entities, generates agent personas, runs dual-platform simulations, and produces structured reports with interactive follow-up tools.

## Workflow

1. Graph Build
2. Environment Setup
3. Simulation Run
4. Report Generation
5. Deep Interaction

## Quick Start

### Prerequisites

- Node.js `18+`
- Python `3.11` to `3.12`
- `uv`

### Setup

```bash
cp .env.example .env
npm run setup:all
```

Set these keys in `.env`:

- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_MODEL_NAME`
- `ZEP_API_KEY`

### Run

```bash
npm run dev
```

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:5001`

## Docker

```bash
cp .env.example .env
docker compose up -d
```

## License

AGPL-3.0