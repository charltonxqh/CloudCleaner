# CloudCleaner

CloudCleaner finds AWS resources nobody is using, proves they're unused, works out what order they
have to be deleted in, and asks a human before touching anything.

---

## The problem

Stopping an EC2 instance doesn't stop the bill.

The compute charge goes away, but the EBS volumes attached to it keep billing, and so does the
public IPv4 address. A stopped `t3.micro` with a 16 GB volume and an Elastic IP still costs about
**$4.93 a month, forever**. Multiply that by every proof-of-concept box a team has ever stopped
"for now" and it adds up quietly.

So the only real fix is deleting things. And deleting things in AWS is where people give up,
because the dependencies bite:

- You can't release an Elastic IP while it's still associated with something.
- A volume with `DeleteOnTermination=false` outlives the instance it was attached to, and keeps
  charging you after the instance is gone.
- AWS tells you about these one blocker at a time. Fix one, retry, hit the next.

Most cleanup tools stop when they hit a dependency and tell you to sort it out yourself.
CloudCleaner builds the whole dependency graph up front and topologically sorts it, so the entire
teardown sequence is known before anything runs. That's in `policy/dependencies.py`, and it's the
part of this project worth looking at first.

## What it does

```text
DETECT → INVESTIGATE → ASSESS → PLAN → SAFETY → APPROVAL → EXECUTE → VERIFY → ROLLBACK → RECORD
```

**DETECT** lists EC2 instances, EBS volumes and Elastic IPs, and ranks them by *wasted* spend rather
than total spend — a busy production box is expensive, not wasteful, and shouldn't come top.

**INVESTIGATE** gathers the evidence through read-only MCP tools: CloudWatch CPU and network,
what the resource costs, and GitHub signals — last commit, whether the branch still exists, PR
status and recent CI activity. If the repo that owns a resource is still alive, that matters more
than a low CPU reading.

**ASSESS** hands the evidence to an LLM, which returns a typed verdict — `keep`, `investigate_more`,
`stop` or `retire` — with a reason and a confidence. A deterministic rules engine sees exactly the
same evidence and takes over whenever the model is disabled or fails, so the pipeline never depends
on the LLM being available.

**PLAN** turns a `retire` into an ordered teardown based on the resource dependency graph.

**SAFETY** scores risk and applies hard deterministic gates before execution. Protected environments,
protected tags and unsafe plans are blocked without relying on the LLM.

**APPROVAL** stops and waits for a human, via the UI or Slack.

**EXECUTE** performs only the approved actions. **VERIFY** re-reads the resource state afterwards
instead of assuming an API call succeeded. If a recoverable action fails, **ROLLBACK** restores the
safe state where possible.

**RECORD** writes the run, decision and reasoning trail to SQLite so later investigations can see
what was previously decided.

Dry run is the default. Irreversible steps are labelled, and a snapshot is taken before destructive
volume operations. Protected environments and tags block planning outright. Nothing executes
without a human approval that names the resource.

## Why this is agentic

CloudCleaner separates reasoning from control.

The model is allowed to interpret ambiguous evidence — whether an idle resource still appears to
have a purpose, how GitHub activity changes the picture, and whether the evidence supports keeping,
stopping or retiring it.

It is **not** allowed to directly decide how AWS should be mutated.

```text
LLM recommendation
        ↓
deterministic safety policy
        ↓
dependency-aware teardown plan
        ↓
human approval
        ↓
controlled execution
        ↓
verification / rollback
```

The model reasons; deterministic systems control execution.

## Quick start

You need **Python 3.12+**, **Node 20+**, and [**uv**](https://docs.astral.sh/uv/). If you don't have
uv yet:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh          # macOS / Linux
```

```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"   # Windows
```

> **Windows users, two things that will bite you.** PowerShell has no inline environment variable
> prefix, so `CLOUDCLEANER_PROVIDER=fixture uv run ...` fails — set the variable on its own line
> first. And Windows PowerShell 5.1 (the one that ships with Windows) doesn't support `&&`, so put
> each command on its own line. PowerShell 7+ and the commands below handle both. Everything else
> is the same on all three platforms.

### Try it with no AWS account

The fastest way to see it work. There's a built-in demo account in `fixtures/demo.py` that the graph
can't tell apart from the real thing, so the whole pipeline runs offline — no AWS credentials and
nothing to clean up afterwards.

```bash
# macOS / Linux
cd agent
uv sync --dev

CLOUDCLEANER_PROVIDER=fixture uv run python -m cloudcleaner.cli scan
```

```powershell
# Windows (PowerShell)
cd agent
uv sync --dev

$env:CLOUDCLEANER_PROVIDER = "fixture"
uv run python -m cloudcleaner.cli scan
```

Either way you get:

```text
provider=fixture  dry_run=True

RESOURCE                   TYPE   STATE              $/MO
i-0999prod888              ec2    running          $34.37
vol-0orphan11              ebs    available         $8.00 *
i-0abc123def456789         ec2    stopped           $4.93 *
eipalloc-0unused9          eip    unassociated      $3.65 *

4 resources · $50.95/mo total · $16.58/mo not running but still billing (*)
```

Then let it reason about all of them and plan the teardowns. On Windows the `$env:` line above is
still set for the rest of the session, so you only need it once:

```bash
uv run python -m cloudcleaner.cli sweep
```

That prints a verdict per resource, the ordered steps for anything it wants to retire, and what
you'd recover per month.

Fixture mode replaces the external AWS and GitHub evidence sources with deterministic demo data.
It does **not** replace the agent pipeline: assessment, planning, safety checks, approval logic,
persistence and the rest of the workflow still run normally.

### Set up for real

Copy the template and fill it in. `.env` goes at the **repo root**, not inside `agent/`:

```bash
cp .env.example .env            # works in PowerShell too (cp is aliased to Copy-Item)
```

```text
CloudCleaner/
├── .env          ← here
├── agent/
└── app/
```

You need `GROQ_API_KEY` and AWS credentials.
`GITHUB_TOKEN` is optional but makes the verdicts noticeably better. Then check it's all wired up:

```bash
# macOS / Linux
cd agent && uv run python -m cloudcleaner.cli doctor
```

```powershell
# Windows (PowerShell)
cd agent
uv run python -m cloudcleaner.cli doctor
```

```text
config file   /path/to/CloudCleaner/.env
data dir      /path/to/CloudCleaner/output
provider      fixture
dry run       True
model         disabled, rules only

[ok ] Groq key
[ok ] AWS not needed — running against the built-in demo account
[ok ] GitHub token
```

**That first line is the important one.** `doctor` prints the `.env` it actually found, which is
almost always the answer when a key "isn't working". If it says it found nothing, or found a
different file than you expected, set `CLOUDCLEANER_ENV_FILE` to an absolute path and it will stop
searching.

### Run the UI

Install the frontend dependencies once:

```bash
cd app
npm install
```

For the normal AWS-backed version:

```bash
npm run dev
```

For the deterministic fixture/demo version:

```bash
# macOS / Linux
CLOUDCLEANER_PROVIDER=fixture npm run dev
```

```powershell
# Windows (PowerShell)
$env:CLOUDCLEANER_PROVIDER = "fixture"
npm run dev
```

One command starts both the dashboard on **http://localhost:3000** and the API on **:8123**.

The UI includes the resource inventory, investigation view, live agent trace, history, monitoring
state and evaluation results. Select a resource to investigate it and watch the reasoning trail
build as the agent moves through evidence gathering, assessment, planning and safety checks.

If startup reports that ports `3000` or `8123` are already in use, check whether another local
CloudCleaner or Docker process is still running before starting another instance.

If the combined command fails on Windows, run the two halves in separate terminals:

```powershell
# terminal 1
cd app
npm run dev:ui

# terminal 2
cd agent
uv run main.py
```

(`npm run dev:debug` sets an environment variable inline, so that one really doesn't work on
Windows. Use the two-terminal version instead.)

### Docker

CloudCleaner can also run as three containers:

```text
frontend
    ↓
backend
    ↓
MCP server
```

From the repository root:

```bash
docker compose up --build
```

The Compose stack runs:

- Next.js frontend on `:3000`
- FastAPI/LangGraph backend on `:8123`
- MCP investigation server on `:8130`

The MCP server is used internally by the backend and exposes read-only investigation tools rather
than destructive cloud operations.

Stop the stack with:

```bash
docker compose down
```

### The CLI

Every command works with or without AWS, depending on `CLOUDCLEANER_PROVIDER`.

```bash
cd agent

uv run python -m cloudcleaner.cli doctor                    # check credentials and config
uv run python -m cloudcleaner.cli scan                      # what exists and what it costs
uv run python -m cloudcleaner.cli sweep                     # investigate everything, plan teardowns
uv run python -m cloudcleaner.cli investigate i-0abc123     # dig into one resource
uv run python -m cloudcleaner.cli investigate i-0abc123 --force-plan   # plan even if the verdict was 'keep'
uv run python -m cloudcleaner.cli history                   # past runs and what you actually saved
uv run python -m cloudcleaner.cli history --limit 100
uv run python -m cloudcleaner.cli serve --port 8123         # the HTTP API on its own
```

Those are identical on Windows — it's only the environment variables in front that change.

To switch between the demo account and real AWS for one session:

```bash
export CLOUDCLEANER_PROVIDER=fixture     # macOS / Linux
```

```powershell
$env:CLOUDCLEANER_PROVIDER = "fixture"   # Windows (PowerShell)
```

Or just set `CLOUDCLEANER_PROVIDER` in `.env` and forget about it.

### Tests

```bash
cd agent
uv run pytest
```

The test suite runs without an AWS account. It includes Hypothesis property tests over the dependency
graph — the ordering guarantees are checked against generated graphs, not just hand-written examples.

### Installing it

Published to PyPI, so you can skip the checkout entirely:

```bash
pip install "cloudcleaner-agent[server]"
cloudcleaner doctor
```

Same commands, installed as `cloudcleaner`. On Windows, if `cloudcleaner` isn't found after
installing, pip's scripts directory isn't on your PATH — `python -m cloudcleaner.cli doctor` works
regardless.

## MCP investigation layer

CloudCleaner uses the Model Context Protocol (MCP) as the boundary between agent reasoning and
external investigation tools.

```text
LangGraph agent
      │
      ▼
  MCP client
      │
      ▼
  MCP server
   ├── AWS / boto3
   └── GitHub API
```

The MCP layer is deliberately **read-only**. It currently exposes:

| MCP tool | Purpose |
|---|---|
| `list_ec2_instances` | Discover EC2 resources and metadata |
| `list_volumes` | Discover EBS volumes and attachment state |
| `list_elastic_ips` | Discover Elastic IP allocations |
| `get_ec2_usage_evidence` | Gather usage evidence for an EC2 resource |
| `get_github_evidence` | Gather repository, branch, PR, CI and commit evidence |

Destructive operations are intentionally not exposed as general-purpose MCP tools.

A recommendation therefore cannot turn directly into an arbitrary cloud API call. Execution stays
inside CloudCleaner's deterministic policy, approval and execution path.

This keeps the boundary simple:

```text
MCP       → investigate
LLM       → reason
Policy    → constrain
Human     → approve
Executor  → act
Verifier  → confirm
```

## Continuous monitoring

Cloud waste changes over time. A resource that is justified today can become abandoned after a
branch is merged, a proof of concept ends, or an owner stops using it.

CloudCleaner therefore supports continuous lightweight monitoring rather than treating cleanup as
a one-off scan.

The monitoring loop:

1. scans the current resource inventory;
2. fingerprints relevant resource state;
3. detects new or changed resources;
4. reuses recent investigations when nothing meaningful changed;
5. reassesses resources after a configurable interval;
6. suppresses duplicate approval notifications;
7. persists monitoring state between scans.

Monitoring can run automatically or be triggered through the HTTP API.

Relevant configuration:

```text
CLOUDCLEANER_MONITOR_INTERVAL_MINUTES
CLOUDCLEANER_MONITOR_REASSESS_MINUTES
CLOUDCLEANER_MONITOR_ON_STARTUP
CLOUDCLEANER_MONITOR_API_KEY
```

`CLOUDCLEANER_MONITOR_INTERVAL_MINUTES=0` disables scheduled monitoring.

## Human-in-the-loop approval

Recommendations are not execution permissions.

When CloudCleaner finds an actionable resource, the workflow can pause for human approval through
the UI or Slack. The approval is tied to the resource and proposed action rather than giving the
agent unrestricted permission to mutate AWS.

Slack supports:

- approve;
- reject;
- email the resource owner.

Slack interaction signatures are verified before an approval is accepted.

Owner notifications can be sent through Amazon SES.

## Evaluation

An agent that produces convincing explanations but unreliable actions is not useful for cloud
operations. CloudCleaner therefore evaluates both the reasoning layer and the deterministic
execution pipeline.

The evaluation framework tracks six primary metrics:

| Metric | What it measures |
|---|---|
| **Human Acceptance Rate** | How often human reviewers accept the agent's recommendation |
| **Structured LLM Output Success** | Whether model responses satisfy the expected typed output schema |
| **Average LLM Cost** | Average model cost per investigation |
| **Tool-call Success Rate** | Reliability of external evidence/tool calls |
| **Teardown-plan Correctness** | Whether generated teardown steps satisfy dependency ordering |
| **Savings Accuracy** | Whether estimated recoverable spend matches the expected resource costs |

This makes it possible to evaluate CloudCleaner as a system rather than evaluating the LLM in
isolation.

## Configuration

All of it goes in `.env` at the repo root. `agent/cloudcleaner/config.py` looks at
`CLOUDCLEANER_ENV_FILE` first, then searches upward from the working directory, then from the
package, then `~/.cloudcleaner/.env`. Run `cloudcleaner doctor` to see which one it settled on.

| Variable | Default | What it does |
|---|---|---|
| `GROQ_API_KEY` | — | The reasoning model |
| `GROQ_MODEL` | `openai/gpt-oss-20b` | Which Groq model to use |
| `OPENAI_API_KEY` | — | Optional OpenAI credential when required by configured integrations |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_SESSION_TOKEN` | — | AWS credentials; boto3 reads these exact uppercase names |
| `AWS_REGION` | `us-east-1` | AWS region to investigate |
| `GITHUB_TOKEN` | — | Read-only GitHub token for repository evidence |
| `GITHUB_REPO` | — | Optional repository context |
| `CLOUDCLEANER_PROVIDER` | `aws` | `fixture` uses deterministic demo evidence |
| `CLOUDCLEANER_DRY_RUN` | `true` | Plan and log everything without making real changes |
| `CLOUDCLEANER_AI_ENABLED` | `true` | `false` = deterministic rules only |
| `METRIC_WINDOW_DAYS` | `7` | How far back CloudWatch is queried |
| `CLOUDCLEANER_DATA_DIR` | `output/` | Where the database and reasoning log are written |
| `CLOUDCLEANER_ENV_FILE` | — | Absolute path to a specific `.env` |
| `AWS_ENDPOINT_URL` | — | Point boto3 at an alternative AWS-compatible endpoint |
| `SLACK_BOT_TOKEN` | — | Slack bot credential for approval messages |
| `SLACK_SIGNING_SECRET` | — | Verifies Slack interaction requests |
| `SLACK_CHANNEL_ID` | — | Channel used for approval requests |
| `SES_FROM_EMAIL` | — | Verified SES sender address |
| `CLOUDCLEANER_DEFAULT_OWNER_EMAIL` | — | Fallback owner email |
| `CLOUDCLEANER_MONITOR_INTERVAL_MINUTES` | `0` | Scheduled monitoring interval; `0` disables it |
| `CLOUDCLEANER_MONITOR_REASSESS_MINUTES` | `60` | Reassess unchanged resources after this interval |
| `CLOUDCLEANER_MONITOR_ON_STARTUP` | — | Run monitoring when the backend starts |
| `CLOUDCLEANER_MONITOR_API_KEY` | — | Protects monitoring trigger endpoints |

**Turning it loose.** `CLOUDCLEANER_DRY_RUN=false` is the switch between simulation and real
execution. Everything else — approval gates, safety rules, dependency ordering and verification —
still applies, but change it deliberately.

## How it's built

| Layer | Choice |
|---|---|
| Frontend | Next.js 16, React 19, Tailwind v4 |
| Frontend ↔ agent | AG-UI / CopilotKit |
| Backend | FastAPI on `:8123` |
| Orchestration | LangGraph 1.1 — stateful graph with conditional routing and human interruption |
| Agent ↔ tools | MCP |
| Investigation | MCP server backed by boto3 and the GitHub API |
| Persistence | SQLite — checkpoints plus runs / decisions / events / snapshots |
| LLM | Groq via `langchain-groq`, structured output through `json_schema` |
| Cloud | boto3 → EC2, EBS, Elastic IPs, CloudWatch, STS, Price List |
| Notifications | Slack approvals and owner email via SES |
| Schemas | Pydantic v2 |
| Containers | Docker / Docker Compose |

The pipeline is real end to end — fixture mode substitutes deterministic external evidence, not
mocked graph nodes. Assessment, safety, planning, approval, persistence, execution logic,
verification and rollback use the same pipeline in fixture and AWS modes.

The investigation layer is separated from execution intentionally. MCP provides read-only evidence;
the model produces a recommendation; deterministic policy and dependency logic decide what can
proceed; a human grants approval; and only then can the executor act.

| Where to look | What's there |
|---|---|
| `policy/dependencies.py` | Kahn's algorithm with cycle detection — the teardown ordering |
| `tools/aws/cost.py` | Price List lookups with local fallbacks; separates cost-while-stopped from cost-while-running |
| `policy/risk.py`, `safety.py` | Risk scoring and hard gates, checked before execution |
| `tools/github/` | Commits, branches, PRs and CI evidence |
| `mcp/server.py` | Read-only MCP investigation tools |
| `mcp/client.py` | MCP client used by the agent/provider layer |
| `storage/` | Run history and prior human decisions |
| `monitoring.py` | Continuous scan/reassessment loop |
| `fixtures/demo.py` | Deterministic offline demo account |
| `scripts/` | Connection smoke tests and evaluation harness |

## Repository layout

```text
CloudCleaner/
├── agent/
│   ├── cloudcleaner/
│   │   ├── graph/               # LangGraph state, nodes and conditional routing
│   │   ├── policy/              # dependency ordering, risk, safety, approval
│   │   ├── tools/               # AWS, GitHub, Slack, email and provider dispatch
│   │   ├── mcp/
│   │   │   ├── client.py        # MCP client used by CloudCleaner
│   │   │   └── server.py        # read-only AWS/GitHub MCP tools
│   │   ├── storage/             # SQLite schema + repository
│   │   ├── evidence/            # reasoning-trail collector
│   │   ├── fixtures/demo.py     # deterministic demo account
│   │   ├── monitoring.py        # continuous resource monitoring
│   │   ├── cli.py               # scan / sweep / investigate / history / doctor / serve
│   │   └── server.py            # FastAPI application
│   ├── scripts/                 # connection smoke tests + evaluation harness
│   ├── tests/                   # automated tests
│   ├── main.py                  # backend entrypoint used by npm run dev
│   ├── Dockerfile
│   └── pyproject.toml
├── app/
│   ├── src/
│   │   ├── app/page.tsx         # dashboard
│   │   ├── components/cloudcleaner/   # views, shell and UI components
│   │   └── lib/api.ts           # typed backend client
│   ├── scripts/
│   ├── Dockerfile
│   └── package.json
├── output/
│   ├── cloudcleaner.db          # local SQLite state
│   └── monitoring.json          # monitoring state
├── docker-compose.yml
└── .env.example
```

## Safety model

CloudCleaner assumes that deleting the wrong resource is more expensive than missing one cleanup
opportunity.

Safety is therefore layered:

1. **Evidence before recommendation** — usage, cost and ownership context are gathered first.
2. **Typed recommendation** — the model can only return supported verdicts.
3. **Deterministic policy** — hard rules do not depend on model judgement.
4. **Protected-resource gates** — production/protected resources can be blocked outright.
5. **Dependency ordering** — teardown order is computed before execution.
6. **Human approval** — actionable remediation pauses for explicit approval.
7. **Dry run by default** — real mutation is opt-in.
8. **Pre-destructive recovery** — recoverable state such as EBS snapshots is created before
   irreversible steps where applicable.
9. **Verification** — CloudCleaner re-reads state after execution.
10. **Rollback** — recoverable failed operations can be compensated instead of silently continuing.

## Known gaps

Worth saying out loud rather than letting you find them:

- **Snapshots are listed and priced but never scanned as first-class cleanup candidates** —
  `detect_node` doesn't call `list_snapshots()` yet.
- **The frontend still carries unused CopilotKit starter code** —
  `app/src/app/declarative-generative-ui/`, the a2ui hooks, and `agent/src/`. The CloudCleaner UI
  never imports any of it.
- **Coverage is currently focused on three resource types:** EC2, EBS and Elastic IPs. RDS, NAT
  gateways, load balancers and ElastiCache are natural next targets.
- **GitHub evidence depends on repository metadata being available.** Resources without useful
  ownership/repository tags have less lifecycle context to reason over.
- **Rollback is necessarily action-specific.** Some destructive cloud operations cannot be perfectly
  reversed, which is why CloudCleaner combines snapshots, irreversible-step labels and human
  approval rather than claiming every action is reversible.
