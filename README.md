# ChainRisk

Supply chain decision intelligence platform for scenario simulation, disruption analysis, and action-focused reporting.

Repository: [samirsawarkar/chainrisk](https://github.com/samirsawarkar/chainrisk)

## What ChainRisk Solves

ChainRisk helps operations and strategy teams answer practical questions such as:

- What happens to backlog, service level, and lead time if a supplier fails?
- Which node (supplier, manufacturer, distributor, retailer) amplifies risk the most?
- How much buffer stock or capacity change is needed to stabilize the network?
- Which intervention gives the highest impact per cost under uncertainty?

The system turns your supply chain context into a simulation-ready model, runs scenario stress tests, and returns analysis outputs you can act on.

## End-to-End Supply Chain Workflow

### Step 1 - Project Intake and Context Build

**Input**
- Source files (PDF/MD/TXT): network design notes, SOPs, demand assumptions, risk registers
- Natural-language simulation objective

**What the system does**
- Parses and chunks source material
- Builds entity/relation memory graph
- Infers initial domain ontology and scenario context

**Output**
- Structured project context
- Graph foundation for downstream simulation
- Traceable source-grounded memory for analysis

### Step 2 - Model and Environment Setup

**Input**
- Graph context from step 1
- Simulation settings (rounds/time horizon, platform parameters)

**What the system does**
- Generates simulation entities and behavior settings
- Prepares dual-world simulation environment
- Produces baseline supply chain configuration for execution

**Output**
- Simulation-ready project state
- Config artifacts for reproducible runs
- Baseline assumptions visible before execution

### Step 3 - Scenario Execution

**Input**
- Prepared simulation environment
- Optional stressors (capacity constraints, delays, shocks)

**What the system does**
- Runs iterative simulation rounds
- Updates memory as state evolves
- Tracks system-level and node-level changes over time

**Output**
- Full run history and state transitions
- Time-series signals for instability, recovery, and amplification
- Machine-readable data for reports and visualizations

### Step 4 - Analysis and Report Generation

**Input**
- Simulation outputs from step 3

**What the system does**
- Synthesizes key findings with tool-assisted retrieval
- Connects outcomes to entities, edges, and causal chains
- Produces structured report sections automatically

**Output-oriented deliverables**
- Key risk findings and evidence-backed narrative
- Bottleneck and amplification diagnosis
- Impact summary by scenario and intervention
- Action recommendations linked to observed dynamics

### Step 5 - Interactive Exploration and What-If

**Input**
- Existing report, graph memory, and simulation state

**What the system does**
- Lets users drill down on findings
- Supports follow-up queries and targeted scenario checks
- Enables iterative refinement of decisions

**Output**
- Decision-ready follow-up insights
- Clarified trade-offs between competing actions
- Faster move from analysis to execution plan

## Analysis Outputs You Can Expect

ChainRisk is designed to be output-first. Typical outputs include:

- **Risk Amplification Signals**: where demand variability is magnified across tiers
- **Backlog and Flow Health**: backlog trend, throughput pressure, and recovery trajectory
- **Capacity Stress Map**: node-level stress and utilization hotspots
- **Causality Trail**: why a KPI moved, not just that it moved
- **Intervention Comparison**: side-by-side effect of alternative actions
- **Execution Recommendations**: concrete next actions tied to model evidence

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

### Run (Local Development)

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