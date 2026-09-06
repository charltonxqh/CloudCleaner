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

```
DETECT → INVESTIGATE → ASSESS → POLICY → PLAN → APPROVAL → EXECUTE → VERIFY → (ROLLBACK) → RECORD
```

**DETECT** lists EC2 instances, EBS volumes and Elastic IPs, and ranks them by *wasted* spend rather
than total spend — a busy production box is expensive, not wasteful, and shouldn't come top.

**INVESTIGATE** gathers the evidence: CloudWatch CPU and network, what it costs, and GitHub signals
— last commit, whether the branch still exists, PR status, last CI run. If the repo that owns a
resource is still alive, that matters more than a low CPU reading.

**ASSESS** hands the evidence to an LLM, which returns a typed verdict — `keep`, `investigate_more`,
`stop` or `retire` — with a reason and a confidence. A deterministic rules engine sees exactly the
same evidence and takes over whenever the model is disabled or fails, so the pipeline never depends
on the LLM being available.

**POLICY** scores risk and applies hard safety gates. No LLM involved.

**PLAN** turns a `retire` into an ordered teardown. **APPROVAL** stops and waits for a human, via
the UI or Slack. **EXECUTE**, **VERIFY** and **ROLLBACK** do the work, confirm it landed, and undo
it if it didn't. **RECORD** writes the run, the decision and the full reasoning trail to SQLite, so
the next run remembers what you already decided.

Dry run is the default. Irreversible steps are labelled, and a snapshot is taken before them.
Protected environments and tags block planning outright. Nothing executes without a human approval
that names the resource.

## Quick start

### Try it with no AWS account

The fastest way to see it work. There's a built-in demo account in `fixtures/demo.py` that the graph
can't tell apart from the real thing, so the whole pipeline runs offline:

```bash
cd agent
uv sync --dev

CLOUDCLEANER_PROVIDER=fixture uv run python -m cloudcleaner.cli scan
```

```
provider=fixture  dry_run=True

RESOURCE                   TYPE   STATE              $/MO
i-0999prod888              ec2    running          $34.37
vol-0orphan11              ebs    available         $8.00 *
i-0abc123def456789         ec2    stopped           $4.93 *
eipalloc-0unused9          eip    unassociated      $3.65 *

4 resources · $50.95/mo total · $16.58/mo not running but still billing (*)
```

Then let it reason about all of them and plan the teardowns:

```bash
CLOUDCLEANER_PROVIDER=fixture uv run python -m cloudcleaner.cli sweep
```

That prints a verdict per resource, the ordered steps for anything it wants to retire, and what
you'd recover per month. No AWS credentials, no Groq key, nothing to clean up afterwards.

### Set up for real

Copy the template and fill it in:

```bash
cp .env.example .env
```

You need `GROQ_API_KEY` (free at [console.groq.com](https://console.groq.com)) and AWS credentials.
`GITHUB_TOKEN` is optional but makes the verdicts noticeably better. Then check everything is wired
up:

```bash
cd agent && uv run python -m cloudcleaner.cli doctor
```

```
config file   /path/to/CloudCleaner/.env
data dir      /path/to/CloudCleaner/output
provider      fixture
dry run       True
model         disabled, rules only

[ok ] Groq key
[ok ] AWS not needed — running against the built-in demo account
[ok ] GitHub token
```

`doctor` tells you which `.env` it actually found, which is usually the answer when something isn't
being picked up.

### Run the UI

```bash
cd app
npm install
npm run dev
```

One command starts both: the dashboard on **http://localhost:3000** and the API on **:8123**. The UI
has five views — overview, resources, investigation, history and evaluation. Click any resource to
investigate it and watch the reasoning trail build up as the agent works.

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

### Tests

```bash
cd agent && uv run pytest
```

111 tests, no AWS account needed. Includes Hypothesis property tests over the dependency graph —
the ordering guarantees are checked against generated graphs, not just hand-written examples.

### Installing it

Published to PyPI, so you can skip the checkout entirely:

```bash
pip install "cloudcleaner-agent[server]"
cloudcleaner doctor
```

Same commands, installed as `cloudcleaner`.

## Configuration

All of it goes in `.env` at the repo root. `agent/cloudcleaner/config.py` searches upward from the
working directory, then from the package, then `~/.cloudcleaner/.env`.

| Variable | Default | What it does |
|---|---|---|
| `GROQ_API_KEY` | — | The reasoning model. Free tier is fine. |
| `GROQ_MODEL` | `openai/gpt-oss-20b` | Which Groq model to use |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_SESSION_TOKEN` | — | Must be uppercase; boto3 only reads these exact names |
| `AWS_REGION` | `us-east-1` | Access-denied errors are usually the wrong region |
| `GITHUB_TOKEN` | — | Read-only PAT. Contents, Pull requests, Actions. |
| `CLOUDCLEANER_PROVIDER` | `aws` | `fixture` runs entirely offline |
| `CLOUDCLEANER_DRY_RUN` | `true` | Plan and log everything, change nothing |
| `CLOUDCLEANER_AI_ENABLED` | `true` | `false` = rules only, no resource metadata leaves the machine |
| `METRIC_WINDOW_DAYS` | `7` | How far back CloudWatch is queried |
| `CLOUDCLEANER_DATA_DIR` | `output/` | Where the database and reasoning log are written |
| `AWS_ENDPOINT_URL` | — | Point boto3 at LocalStack instead of real AWS |
| `SLACK_BOT_TOKEN` / `SLACK_SIGNING_SECRET` / `SLACK_CHANNEL_ID` | — | Approvals from Slack |
| `CLOUDCLEANER_MONITOR_INTERVAL_MINUTES` | `0` | Re-scan on a schedule. `0` disables it. |

**Turning it loose.** `CLOUDCLEANER_DRY_RUN=false` is the only thing standing between a plan and a
real deletion. Everything else — approval gates, safety rules, dependency ordering — still applies,
but do it deliberately.

## How it's built

| Layer | Choice |
|---|---|
| Frontend | Next.js 16, React 19, Tailwind v4 |
| Backend | FastAPI on :8123, with an AG-UI/CopilotKit endpoint mounted at `/` |
| Orchestration | LangGraph 1.1 — 10 nodes, 6 conditional edges, `interrupt()` for approval |
| Persistence | SQLite — `SqliteSaver` checkpoints plus `runs` / `decisions` / `events` / `snapshots` |
| LLM | Groq via `langchain-groq`, structured output through `json_schema` |
| Cloud | boto3 → EC2, CloudWatch, STS |
| Notifications | Slack approvals (Block Kit, signature verified), owner email via SES |
| Schemas | Pydantic v2 |

The pipeline is real end to end — no mocked nodes. `investigate` queries CloudWatch, `execute` calls
boto3, `verify` re-reads actual state, and `routing.py` branches on the verdict so a `keep` never
reaches the approval gate.

| Where to look | What's there |
|---|---|
| `policy/dependencies.py` | Kahn's algorithm with cycle detection — the teardown ordering |
| `tools/aws/cost.py` | Price List lookups with local fallbacks; separates cost-while-stopped from cost-while-running |
| `policy/risk.py`, `safety.py` | Risk scoring and hard gates, run at assess time *and* again at execute time |
| `tools/github/` | Commits, branches, PRs, CI runs |
| `storage/` | Run history, and prior human decisions fed back into the prompt |
| `monitoring.py` | Scheduled re-scan loop, also triggerable over HTTP |
| `fixtures/demo.py` | The offline demo account |

## Repository layout

```
CloudCleaner/
├── agent/
│   ├── cloudcleaner/
│   │   ├── graph/               # LangGraph state, 10 nodes, conditional routing
│   │   ├── policy/              # dependencies (teardown order), risk, safety, approval
│   │   ├── tools/               # aws/, github/, slack/, email/, provider dispatch
│   │   ├── storage/             # SQLite schema + repository (history, memory)
│   │   ├── evidence/            # reasoning-trail collector
│   │   ├── fixtures/demo.py     # offline demo account
│   │   ├── cli.py               # scan / sweep / investigate / history / doctor / serve
│   │   └── server.py            # the FastAPI app (both entrypoints serve this)
│   ├── scripts/                 # connection smoke tests + evaluation harness
│   ├── tests/                   # 111 tests
│   ├── main.py                  # thin shim over server.py, run by `npm run dev`
│   └── pyproject.toml           # published to PyPI as cloudcleaner-agent
├── app/
│   ├── src/
│   │   ├── app/page.tsx         # the dashboard
│   │   ├── components/cloudcleaner/   # views, shell, primitives, pixel art
│   │   └── lib/api.ts           # typed client for the backend
│   ├── scripts/                 # logo + diagram generators
│   └── package.json
└── .env.example
```

## Known gaps

Worth saying out loud rather than letting you find them:

- **Nothing has run against a real AWS account.** Every boto3 path is exercised through fixtures.
- **Snapshots are listed and priced but never scanned** — `detect_node` doesn't call
  `list_snapshots()` yet.
- **The frontend still carries unused CopilotKit starter code** —
  `app/src/app/declarative-generative-ui/`, the a2ui hooks, and `agent/src/`. The CloudCleaner UI
  never imports any of it, and it's the source of the only TypeScript errors in the project.
- **Coverage is three resource types.** RDS, NAT gateways, load balancers and ElastiCache are the
  obvious next ones, and they're where the bigger money usually hides.
