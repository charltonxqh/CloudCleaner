# CloudCleaner

An agentic AI system that investigates idle cloud resources, gathers evidence from AWS + GitHub/CI,
recommends an action, asks a human to approve it, then executes and verifies it.

Built for the **IGNITE Agentic AI Hackathon 2026** (SimplifyNext) — **Software AI track**.

---

## Part 1 — What this repo does today

### 1.1 The idea

Cloud accounts accumulate resources nobody dares delete, because nobody can prove they are unused.
CloudCleaner is a **decision-support + transaction agent** that builds the proof:

```
DETECT  →  INVESTIGATE  →  ASSESS  →  HUMAN APPROVAL  →  EXECUTE  →  VERIFY
```

- **DETECT** — list live AWS resources (currently EC2 instances).
- **INVESTIGATE** — collect evidence: CloudWatch CPU/network, cost, plus GitHub signals (last commit, PR status, whether the branch still exists, last CI run).
- **ASSESS** — an LLM reads only the evidence and returns a typed `Recommendation` (`keep` / `investigate_more` / `stop`) with a reason and confidence.
- **APPROVAL** — human-in-the-loop gate (Slack approval planned).
- **EXECUTE** — perform the approved action (stop, never terminate).
- **VERIFY** — confirm the resource reached the expected state.

Deliberate safety stance already visible in the code: the model is **forbidden from recommending deletion or termination** (`graph/nodes/assess.py`), and the only executable action is `stop`.

### 1.2 Stack

| Layer | Choice |
|---|---|
| Frontend | Next.js 16 + React 19 + CopilotKit 1.70 (AG-UI protocol) |
| Backend | FastAPI + `ag-ui-langgraph`, served by uvicorn on port 8123 |
| Orchestration | LangGraph 1.1 (`StateGraph`, typed `TypedDict` state) |
| LLM | Groq via `langchain-groq` (`openai/gpt-oss-20b` default) |
| Cloud | boto3 → EC2, CloudWatch, STS (region `us-east-1`) |
| Schemas | Pydantic v2 (`cloudcleaner/schemas.py`) |
| Package mgmt | `npm` (frontend), `uv` (backend) |

### 1.3 What is actually implemented

**Working end-to-end:**

- `cloudcleaner/graph/graph.py` — the full 6-node LangGraph compiles and runs (`scripts/run_cloudcleaner.py`).
- `cloudcleaner/graph/state.py`, `cloudcleaner/schemas.py` — typed state and shared Pydantic contracts (`CloudResource`, `AWSEvidence`, `GitHubEvidence`, `Recommendation`, `ApprovalDecision`).
- `cloudcleaner/tools/aws/client.py` — boto3 clients for EC2 / CloudWatch / STS.
- `cloudcleaner/tools/aws/inventory.py` — **real** EC2 listing with pagination, tag flattening into `CloudResource`.
- `cloudcleaner/tools/aws/metrics.py` — **real** CloudWatch 7-day average CPU and NetworkIn/NetworkOut sums.
- `cloudcleaner/graph/nodes/detect.py` — real AWS call, picks the first instance found.
- `cloudcleaner/graph/nodes/assess.py` — real Groq call with `with_structured_output(Recommendation)`.
- Connection smoke tests: `scripts/test_aws_connection.py`, `test_aws_inventory.py`, `test_aws_metrics.py`, `test_groq_connection.py`.

**Stubbed / mocked (known gaps):**

| Gap | File | Note |
|---|---|---|
| Evidence is hardcoded | `graph/nodes/investigate.py` | Returns fixed AWS + GitHub evidence; does **not** call the real `metrics.py` it already has |
| Approval is auto-approve | `graph/nodes/approval.py` | Always returns `approve` by `demo-user` |
| Execute is a print | `graph/nodes/execute.py` | Returns `"MOCK: EC2 instance stopped."` |
| Verify always passes | `graph/nodes/verify.py` | Hardcoded `True` |
| No conditional routing | `graph/routing.py` | Empty — graph is a straight line, so `keep` still flows into approve/execute |
| GitHub tools | `tools/github/*.py` | All empty files |
| Slack tools | `tools/slack/*.py` | All empty files |
| Policy engine | `policy/risk.py`, `policy/safety.py` | Empty — the deterministic safety layer promised in the dev guide doesn't exist yet |
| Evidence collector/formatter | `evidence/*.py` | Empty (also note the typo: `evidence/__init.py` should be `__init__.py`) |
| Storage / memory | `storage/repository.py` | Empty |
| AWS cost / volumes / EIPs / actions | `tools/aws/cost.py`, `volumes.py`, `addresses.py`, `actions.py`, `history.py` | Empty |
| Tests | `tests/*.py` | All four test files are empty |

**Biggest structural gap:** the frontend is still the **CopilotKit starter demo**. `agent/main.py` serves `src.agent.graph` — a todo-list / flight-search / A2UI demo agent on `ChatOpenAI` — not `cloudcleaner.graph.graph`. Nothing in `app/src/src/` mentions CloudCleaner. The agent and the UI are two disconnected projects right now.

### 1.4 Running it

```bash
# frontend + starter agent together
cd app && npm install && npm run dev          # UI on :3000, agent on :8123

# backend only
cd agent && uv sync
uv run python -m scripts.test_aws_connection  # check AWS creds
uv run python -m scripts.run_cloudcleaner     # run the CloudCleaner graph
uv run pytest                                 # (no tests written yet)
```

Full setup, dependency and convention rules: [`agent/README.md`](agent/README.md).

---

## Part 2 — Hackathon brief (Software AI track)

Distilled from the PDFs in [`references/`](references/). The Physical AI / Unitree robot track
(`IGNITE - Agentic AI Hackathon Slides_25 Aug.pdf`) is **out of scope** and excluded here.

### 2.1 The problem statement we must answer

> **Design for a World in Transformation.**
> Change is everywhere — in how we live, learn, and relate to one another. Transformation takes time,
> effort, and the right support at the right moment. Build something that helps: a solution that
> **plans, acts, and adapts over time**. Your team chooses the problem and decides who it serves.
> Design a solution that thinks ahead, takes action, and leaves people genuinely better off.

### 2.2 Key dates

| Date | Milestone |
|---|---|
| 14 Aug | Kick-off |
| 17–28 Aug | Training & mentoring sessions |
| **7 Sep** | **Solution submission** |
| 9–11 Sep | Semi-finals (various locations) |
| 18 Sep | Grand Finale @ NUS |

### 2.3 Deliverables

- **Project files / workflow** — max 5 GB, **one submission only**
- **Presentation deck** — max **10 slides**
- **Demo video** — max **5 minutes** (digital solution walkthrough)

Deliverables must: answer the question (problem + innovative solution), showcase Agentic AI knowledge
(technical soundness and functionality), and create business impact.

### 2.4 Judging criteria — 5 × 20%

| Criterion | Weight | 2 points awarded when… |
|---|---|---|
| Benefits delivered | 20% | Clear benefits; scalable or easily adopted |
| Original / innovative idea | 20% | Unique and innovative approach to the problem |
| Effectiveness of the solution | 20% | Fully addresses and **resolves** the problem |
| Technical quality & superiority | 20% | Technically advanced, fully functional prototype, minimal work to production |
| Presentation | 20% | Clearly explains the problem and demonstrates the benefits |

(1 point = partial, 0 = minimal. Everything is scored out of 2.)

### 2.5 Project-file requirements (what judges open)

1. **A good README suffices** — instructions to run the code, and an overview of each script/file's purpose.
2. **Environment setup** — virtualenv with `requirements.txt`, or Docker. Path variables documented. Secrets in `.env`.
3. **Language** — Python strongly recommended.
4. **Execution** — no extensive test data needed. They check: (a) does it run as shown in the video, (b) does the presented methodology show up at code level (inline documentation helps), (c) testing/evaluation is covered **in the slides**.

### 2.6 How to write the problem statement

Use the **POV format**: *[User] needs [a way to …] because [insight].*

Six ways a problem statement fails:

| Failure | Example that fails |
|---|---|
| The Solution in Disguise | "Students need an AI chatbot for course advice." |
| The Everyone Problem | "People need better access to mental health support." |
| The Missing Because | "Elderly residents need companionship." |
| The Boiling Ocean | "Singapore needs a sustainable food supply chain." |
| The Solved Problem | "Commuters need to know when the next bus arrives." |
| The Comfortable Guess | "Job seekers need help writing resumes." |

Pressure test — every answer must be yes:

1. Can we name **one person** (a role at a moment)?
2. Can we cite **evidence** (figure + source + date)?
3. Would that person **recognise themselves**?
4. Does it **survive a different solution** — would this problem still exist if agentic AI had never been invented?

The problem statement stays technology-free. A **separate** solution overview argues why agentic AI
earns its place: name the planning, the acting and the adapting, and explain what a fixed workflow
would miss. Both are graded.

### 2.7 Agent classes (digital)

Information · Extraction · **Transaction** · **Decision-Support** · Creative/Generative ·
**Orchestration** · Personalized · **Embedded**

> CloudCleaner sits in **Decision-Support + Transaction + Orchestration** (and Embedded, if the Slack
> approval loop lands). Say this explicitly in the deck.

### 2.8 Best practices the graders expect

- **Context rot is real** — build short, single-purpose agents that do one job and exit.
- **Bound every loop** — a hard iteration cap held in state, ignoring the model's judgement.
- **Descriptions are the interface** — tool names/descriptions/param docs are the highest-leverage prompt text.
- **Keep payloads small** — return small typed results; hold large objects in state, not in the prompt.
- Typed state with reducers where nodes write concurrently; `InMemorySaver` + `thread_id` for conversation; read model IDs from a constant; treat `allowed_tools` as a security boundary.
- Error handling: baseline = functional resilience; **going further = make errors actionable for business users**.
- Code readability, logical folder structure (`src/ docs/ data/ tests/`), concise docs.

### 2.9 Evaluation metrics for digital agents (pick some for the deck)

1. **Schema validation pass rate** — outputs that parse/validate first try.
2. **Tool-call success rate** — calls returning a usable result.
3. **Task completion rate** — resolved end to end with no human finishing the job.
4. **Token cost per run** — input + output + cache tokens.
5. **Loop discipline** — iterations per task vs. the cap.
6. **Answer fidelity** — scored against reviewed ground truth (rubric or LLM judge).

> For CloudCleaner these map cleanly: recommendation accuracy against a labelled set of instances,
> boto3 tool-call success rate, % of investigations reaching a decision without human research,
> and cost per investigation.

### 2.10 Deck structure (10 slides)

1. Title & team · 2. Problem & why it matters (with data) · 3. Solution overview · 4. Methodology ·
5. Technical architecture · 6. Innovation & uniqueness · 7. Benefits delivered (quantified) ·
8. Demo preview · 9. Roadmap · 10. Conclusion & call to action

One core message per slide. Use diagrams. Replace "improves efficiency" with "reduces processing time by 30%".

### 2.11 Video structure (5 minutes)

0:00 hook → 0:30 problem in action → 1:00 solution overview → **1:30–3:30 the demo** →
3:30 impact & metrics → 4:15 close. Show the agent **deciding and acting**, narrate the reasoning,
and point at where it plans, acts, and adapts.

### 2.12 AWS account rules and cost limits

- Sign-in: `https://d-9667b91afb.awsapps.com/start`, username `hackathon2026,<group-leader-email>` (note the comma, no spaces). One account leased per team, group leader registers, 2FA secret shared with teammates.
- **Region: `us-east-1`.** Access-denied errors are usually the wrong region.
- **Access keys expire every 12 hours** — re-login through the portal to refresh them, then update `.env`.
- **Budget: $20 revokes account access, $30 terminates the account and its resources.** Monitor the budget bar; reporting lags a few hours. Extra leases are generally not granted.
- **Do not spin up:** OpenSearch, SageMaker real-time endpoints, NAT Gateway, ALB/NLB, Bedrock Provisioned Throughput, or always-on EC2/RDS.
- **Prefer serverless:** Bedrock on-demand (Nova Micro/Lite, Claude Haiku), Lambda (+ Function URLs), DynamoDB on-demand, S3 and S3 Vectors, Bedrock Knowledge Bases.

> ⚠️ **Direct conflict with our demo.** CloudCleaner needs real EC2 instances to detect, and the guide
> says stop and rethink before launching a server. Keep demo instances on the smallest type, run them
> only long enough to generate 7 days of CloudWatch data (or shorten the metric window), and stop
> everything between working sessions. Budget: $20 is the hard wall.

### 2.13 Taught stack vs. our stack

The training taught: Bedrock (`InvokeModel` / Converse / `ChatBedrockConverse`) with Claude Haiku 4.5
as default, LangGraph / DeepAgents / Claude Agent SDK for orchestration, Pydantic schemas, MCP for
tools, AG-UI for the agent-facing UI, OTEL for observability, and Bedrock AgentCore Runtime for
deployment (`@app.entrypoint`, `POST /invocations`, `GET /ping`).

We currently run **Groq + LangGraph + CopilotKit/AG-UI**. Groq is legitimate — Session 1 labs ran
entirely on Groq and it keeps the AWS budget for infrastructure rather than tokens. Worth a line in
the deck explaining the choice, and AgentCore deployment is an obvious roadmap slide.

---

## Repository layout

```
CloudCleaner/
├── app/
│   ├── src/                     # Next.js frontend (still the CopilotKit starter)
│   ├── agent/
│   │   ├── cloudcleaner/        # our agent: graph/, tools/, policy/, evidence/, storage/
│   │   ├── src/                 # CopilotKit starter agent (served by main.py today)
│   │   ├── scripts/             # connection tests + graph runner
│   │   ├── tests/               # empty
│   │   └── main.py              # FastAPI + AG-UI endpoint
│   ├── .env.example
│   └── package.json
├── infra/                       # empty
└── references/                  # hackathon PDFs (source for Part 2)
```

## Reference materials

| File | Track | Contents |
|---|---|---|
| `(Kick-off) Agentic AI Hackathon 2026_14 Aug.pdf` | Both | Problem statement, dates, prizes, tech stack |
| `IGNITE - Agentic AI Hackathon - Session 1_17 Aug.pdf` | Software | LLM foundations, agent anatomy, planning strategies, memory, prompt engineering, Bedrock |
| `IGNITE - Agentic AI Hackathon - Session 2_18 Aug.pdf` | Software | LangGraph state/nodes/edges/routing, DeepAgents, Claude Agent SDK, AgentCore deployment |
| `IGNITE_Agentic_AI_Hackathon_Functional_Training_Session_3_24_Aug.pdf` | Both | Problem framing, agent classes, best practices, case studies, metrics, **judging criteria & submission rules** |
| `IGNITE Hackathon 2026 AWS accounts access guide for students.pdf` | Both | Account leasing, access keys, budget limits, service guidance |
| `IGNITE - Agentic AI Hackathon Slides_25 Aug.pdf` | **Physical — ignored** | Unitree quadruped, SportClient, NaVILA |
