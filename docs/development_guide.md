# CloudCleaner Development Guide

This guide explains the project structure, component ownership, local development setup, dependency management, environment variables, and common commands for the CloudCleaner team.

---

## 1. Project Structure

```text
CloudCleaner/
│
├── agent/                           # Python backend / agent
│   ├── cloudcleaner/
│   │   ├── config.py
│   │   ├── schemas.py               # Shared Pydantic contracts (both workstreams)
│   │   │
│   │   ├── graph/
│   │   │   ├── state.py
│   │   │   ├── graph.py
│   │   │   ├── routing.py
│   │   │   └── nodes/               # detect, investigate, assess, plan,
│   │   │                            # policy_check, approval, execute,
│   │   │                            # verify, rollback, record
│   │   ├── tools/
│   │   │   ├── aws/                 # inventory, metrics, cost, volumes,
│   │   │   │                        # addresses, actions
│   │   │   ├── github/
│   │   │   ├── slack/
│   │   │   └── provider.py          # aws | fixture switch, resolved at call time
│   │   │
│   │   ├── policy/                  # risk scoring, safety rules, dependencies
│   │   ├── evidence/                # reasoning log
│   │   ├── storage/                 # run history
│   │   └── fixtures/                # offline demo stack
│   │
│   ├── scripts/                     # sweep, connection tests, demo setup
│   ├── tests/
│   ├── main.py                      # FastAPI + AG-UI endpoint (port 8123)
│   ├── pyproject.toml               # Python dependencies
│   ├── uv.lock
│   └── .venv/                       # Backend virtual environment
│
├── app/                             # Next.js frontend
│   ├── src/
│   │   ├── app/                     # routes, layout, globals.css
│   │   ├── components/cloudcleaner/ # dashboard UI
│   │   └── lib/api.ts               # typed client for the agent
│   ├── public/
│   ├── package.json                 # Frontend dependencies
│   └── next.config.ts
│
├── output/                          # Runtime artifacts (gitignored)
│   ├── history.jsonl                # run history
│   ├── reasoning.jsonl              # agent reasoning trail
│   └── restore/                     # restore recipes
│
├── docs/                            # Team documentation
├── infra/                           # Deployment / Terraform
├── references/                      # Hackathon PDFs
├── .env                             # Local secrets — never commit
└── .env.example                     # Environment variable template
```

---

## 2. Component Ownership

| Component | Folder / File | Responsibility |
|---|---|---|
| Frontend / UI | `app/src/src/` | React / Next.js pages, components, dashboard, agent UI |
| Agent orchestration / LangGraph | `agent/cloudcleaner/graph/` | LangGraph state, nodes, edges, routing, workflow control |
| AWS integration | `agent/cloudcleaner/tools/aws/` | Boto3 tools for EC2, EBS, Elastic IP, CloudWatch, cost, actions |
| GitHub + CI/CD integration | `agent/cloudcleaner/tools/github/` | Pull requests, branches, GitHub Actions / CI-CD evidence |
| Slack integration | `agent/cloudcleaner/tools/slack/` | Approval messages, Slack interactions, human-in-the-loop actions |
| Evidence package | `agent/cloudcleaner/evidence/` | Collect, combine, and format evidence from AWS / GitHub / CI-CD |
| Safety / policy engine | `agent/cloudcleaner/policy/` | Deterministic safety rules, impact assessment, action gating |
| Storage / agent memory | `agent/cloudcleaner/storage/` | Investigation history, approval records, agent state / memory |
| Shared schemas | `agent/cloudcleaner/schemas.py` | Shared Pydantic models and data contracts |
| Backend configuration | `agent/cloudcleaner/config.py` | Environment variables and application configuration |
| Custom API routes | `agent/cloudcleaner/api/` | Additional FastAPI routes if required |
| Backend tests | `agent/tests/` | Unit and integration tests for agent/backend components |
| Backend utility scripts | `agent/scripts/` | Independent scripts for testing AWS, GitHub, Slack, etc. |
| App-level scripts | `app/scripts/` | Scripts generated or used by the frontend/full application |
| Project documentation | `docs/` | Architecture, agent flow, API contracts, development guide |
| External references | `references/` | Organiser slides, hackathon documents, external reference material |
| Infrastructure / deployment | `infra/` | Terraform, AWS deployment configuration, infrastructure setup |
| Frontend dependencies | `app/src/package.json` | npm packages used by the Next.js frontend |
| Backend dependencies | `agent/pyproject.toml` | Python packages used by the agent/backend |
| Local secrets | `.env` | Actual local API keys and credentials — never commit |
| Environment template | `.env.example` | List of required environment variables without secret values |

---

## 3. First-Time Setup

### 3.1 Clone the repository

```bash
git clone <repository-url>
cd CloudCleaner
```

---

### 3.2 Install frontend dependencies

```bash
cd app
npm install
```

Run `npm install`:

- after cloning the repository for the first time; or
- when `package.json` / `package-lock.json` changes.

---

### 3.3 Install backend dependencies

From the project root:

```bash
cd agent
uv sync
```

`uv sync` reads:

```text
agent/pyproject.toml
```

and creates or updates:

```text
agent/.venv/
```

The backend-local `.venv` is the virtual environment we use for CloudCleaner.

Do not use a separate virtual environment at the project root.

---

### 3.4 After pulling the directory move (one time)

The agent moved from `app/agent/` to `agent/`. A virtualenv stores absolute
paths, so the old one will not work from the new location:

```bash
rm -rf agent/.venv
cd agent && uv sync --dev
```

Backend commands are now `cd agent`, not `cd app/agent`.

---

## 4. Running the Application

### 4.1 Start the frontend / development server

From the project root:

```bash
cd app
npm run dev
```

Open the local URL shown in the terminal, normally:

```text
http://localhost:3000
```

Stop the development server with:

```text
Ctrl + C
```

---

### 4.2 Activate the Python virtual environment

From:

```bash
cd agent
```

On macOS / Linux:

```bash
source .venv/bin/activate
```

You should see something similar to:

```text
(.venv) user@computer agent %
```

Check that the correct Python interpreter is being used:

```bash
which python
```

It should point to:

```text
.../CloudCleaner/agent/.venv/bin/python
```

Deactivate the environment with:

```bash
deactivate
```

### Using `uv` without manually activating `.venv`

You can also run backend commands directly with `uv`:

```bash
uv run python -m scripts.<script_name>
```

For example:

```bash
uv run pytest
```

or:

```bash
uv run python -m scripts.test_aws_connection
```

---

## 5. Adding Dependencies

CloudCleaner has two dependency systems:

```text
Frontend  → npm
Backend   → uv
```

### 5.1 Add a frontend dependency

Go to:

```bash
cd app
```

Then:

```bash
npm install <package-name>
```

Example:

```bash
npm install recharts
```

This updates:

```text
frontend/package.json
app/package-lock.json
```

Commit both files.

---

### 5.2 Add a Python/backend dependency

Go to:

```bash
cd agent
```

Then:

```bash
uv add <package-name>
```

Examples:

```bash
uv add boto3
uv add langchain-groq
uv add python-dotenv
```

This updates:

```text
agent/pyproject.toml
agent/uv.lock
```

Commit both files.

### Project convention

Use:

```bash
uv add <package-name>
```

instead of:

```bash
pip install <package-name>
```

for project dependencies so that dependencies are properly recorded for all teammates.

---

## 6. Environment Variables

Actual local secrets are stored in:

```text
.env
```

Example:

```bash
GROQ_API_KEY=

AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_SESSION_TOKEN=
AWS_REGION=us-east-1

GITHUB_TOKEN=

SLACK_BOT_TOKEN=
SLACK_SIGNING_SECRET=
```

Never commit `.env`.

The repository should contain:

```text
.env.example
```

with the same variable names but no secret values.

After cloning, create your local `.env` with:

```bash
cd app
cp .env.example .env
```

Then fill in your own values.

### Important

Do not expose backend secrets through variables beginning with:

```text
NEXT_PUBLIC_
```

Values using `NEXT_PUBLIC_` can be exposed to browser-side frontend code.

API keys such as `GROQ_API_KEY`, AWS credentials, GitHub tokens, and Slack secrets must remain backend-only.

---

## 7. Common Commands

### Frontend

```bash
cd app
npm install
npm run dev
```

### Backend

```bash
cd agent
uv sync
source .venv/bin/activate
```

### Add frontend dependency

```bash
cd app
npm install <package>
```

### Add backend dependency

```bash
cd agent
uv add <package>
```

### Run backend tests

```bash
cd agent
uv run pytest
```

### Run a backend utility script

```bash
cd agent
uv run python -m scripts.<script_name>
```

---

## 8. Development Conventions

1. Work only in the folder belonging to your assigned component whenever possible.
2. Do not commit `.env`, `.venv/`, API keys, AWS credentials, or other secrets.
3. Do not edit `package.json` or `pyproject.toml` manually just to add a dependency; use `npm install` or `uv add`.
4. Keep LangGraph nodes thin. External API logic should live under `tools/`.
5. Keep destructive AWS actions separated from investigation/read-only tools.
6. Shared input/output structures should use the models defined in `schemas.py`.
7. Test tools independently before integrating them into the LangGraph workflow.
8. Avoid changing generated CopilotKit / AG-UI plumbing unless necessary.
9. Pull the latest changes before starting work and resolve merge conflicts before pushing.
10. Commit dependency lock files whenever dependencies change.

---

## 9. Quick Mental Model

```text
React / Next.js
      ↓
CopilotKit / AG-UI
      ↓
Python backend
      ↓
LangGraph
      ↓
┌─────────┬──────────┬─────────┐
│         │          │         │
AWS     GitHub     Slack      Groq
Boto3     API        API       LLM
```

CloudCleaner's main workflow is:

```text
DETECT
  ↓
INVESTIGATE
  ↓
ASSESS
  ↓
HUMAN APPROVAL
  ↓
EXECUTE
  ↓
VERIFY
  ↓
ROLLBACK / COMPLETE
```
