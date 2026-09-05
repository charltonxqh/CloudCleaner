# CloudCleaner — Project Plan

**Working document for the team. Not the judge-facing README.**
Written 4 Sep 2026. Submission deadline **7 Sep 2026** — 3 days.

---

## 1. The problem

### 1.1 Problem statement (POV format)

> **A cloud engineer at a company running many parallel projects needs a way to fully retire an
> unused project's AWS footprint — not just switch it off — because stopping an instance still
> bills its storage and its public IP, and actually deleting those requires a teardown order that
> AWS reveals only one error message at a time.**

This passes the four pressure tests from Session 3:

| Test | Answer |
|---|---|
| Can we name one person? | The engineer who owns the AWS bill at a team with more projects than people |
| Can we cite evidence? | Yes — AWS's own docs state stopped instances continue to bill EBS. Figures in §1.3 |
| Would they recognise themselves? | This is a first-hand experience from our own team member, not an imagined persona |
| Does it survive a different solution? | Yes. The problem is AWS's billing and dependency model. It exists whether or not anyone builds an agent |

### 1.2 The insight nobody outside AWS expects

**Stopping an EC2 instance releases the compute. It does not release the storage or the address.**

What keeps charging after you press Stop:

| Resource | Why it survives | Rough cost |
|---|---|---|
| Root EBS volume | Detaching compute doesn't deprovision the disk | ~$0.08/GB-month (gp3) |
| Extra data volumes | Often created with `DeleteOnTermination=false` | same |
| Elastic IP / public IPv4 | Billed hourly when not attached to a *running* instance | ~$0.005/hr ≈ $3.60/mo |
| EBS snapshots | Outlive the volume they were taken from | ~$0.05/GB-month |
| NAT Gateway | Entirely independent of the instance | ~$32/mo |
| Load balancer | Same | ~$16/mo |
| Stopped RDS | Still bills storage, **and auto-restarts after 7 days** | varies |

> ⚠️ **Verify every figure against the live AWS pricing page and cite it with a date before it goes
> in the deck.** Session 3 explicitly grades evidence with a source. Do not present these from memory.

### 1.3 The second insight: teardown is a dependency graph

You cannot delete things in the order you think of them. Real constraints:

```
Elastic IP      → must be disassociated before release
Network iface   → must be detached before the subnet can go
Security group  → cannot be deleted while another SG or ENI references it
Subnet          → cannot be deleted while it holds an ENI
Internet GW     → must be detached from the VPC before deletion
VPC             → last, after everything inside it
EBS volume      → survives instance termination when DeleteOnTermination=false
Snapshot        → survives the volume entirely
```

AWS surfaces one blocker per attempt. A human discovers the order by trial and error; a hardcoded
script breaks as soon as the topology differs from the one it was written against.

**This is the agentic justification.** Not "we used an LLM" — but: the graph must be *discovered*
at runtime, the teardown must be *ordered* from what was discovered, and the plan must be *revised*
when a deletion fails for a reason we didn't predict. Plan → act → adapt.

---

## 2. What we are building

### 2.1 One sentence

CloudCleaner finds AWS resources a company has stopped caring about, proves they're unused with
evidence from CloudWatch and GitHub, maps everything they're entangled with, and executes a
dependency-ordered teardown — but only after a human approves the exact plan.

### 2.2 Pipeline

```
DETECT      list EC2 instances, EBS volumes, Elastic IPs, snapshots
   ↓
INVESTIGATE CloudWatch usage + GitHub activity + is this billing while stopped?
   ↓
ASSESS      LLM verdict from evidence only: keep / investigate_more / retire
   ↓
PLAN        NEW — walk the dependency graph, emit an ordered teardown plan with cost per step
   ↓
APPROVAL    human sees the ordered plan and the total monthly saving, then approves or rejects
   ↓
EXECUTE     snapshot first, then run the plan in order, re-planning on failure
   ↓
VERIFY      confirm each resource actually reached the terminal state
```

The **PLAN** node is new and is the centrepiece of the demo. It's what makes this a cloud
*manager* rather than a cloud *stopper*.

### 2.3 Safety model — required, because termination is irreversible

1. **Nothing destructive without approval.** The approval gate is a real LangGraph `interrupt()`, not a mock.
2. **Snapshot before delete.** Every volume gets a snapshot first; the snapshot ID goes in the record.
3. **Dry-run by default.** The plan is fully computed and displayed before anything executes.
4. **Deterministic guardrails outside the LLM** (`policy/safety.py`): never touch anything tagged
   `Environment=prod`, never touch resources younger than N days, never touch untagged resources
   unless explicitly allowed. These are Python `if` statements, not prompt instructions — the model
   cannot talk its way past them.
5. **The LLM recommends. It never executes.** Tool access for destructive actions is gated behind
   the approval decision in state.

### 2.4 What already exists, and why this is still worth building

| Tool | What it does | What it doesn't |
|---|---|---|
| AWS Cost Explorer / Trusted Advisor | Reports spend, flags idle resources | Won't act, won't say what is safe to touch |
| AWS Security Hub | Flags misconfiguration | Same |
| **Cloud Custodian** (CNCF, mature) | Rule-based remediation at scale | Static YAML a human writes and maintains by hand; no reasoning about dependencies; no plain-English justification before it acts |
| **Cloud Janitor** (a prior hackathon project — see §11) | Multi-agent cost + security audit, Terraform remediation, approval gate | *Blocks* resources that have live dependents rather than sequencing a teardown; uses AWS-side signals only |

**The scanning problem is solved industry-wide. The trust problem is not.** Every tool above can tell
you a resource looks idle. None tells you *the order to dismantle it in*, and none looks outside AWS
to ask whether the project that owns it is still alive.

Our two defensible edges:

1. **Evidence from outside AWS.** GitHub/CI correlation — branch deleted, PR merged, no commits in six
   weeks — is what turns "low CPU" into "this project is finished." Nothing in the table above does this.
   *This is the single most important thing to build, because it is the only thing nobody else has.*
2. **Ordered teardown, not just blocking.** Others detect dependents and refuse. We resolve the graph
   and sequence the deletions, re-planning when one fails.

---

## 3. Scope for the next 3 days

### IN

- EC2 instances, EBS volumes, Elastic IPs, snapshots
- Real CloudWatch evidence (CPU + network)
- Real GitHub evidence (last commit, branch existence, PR status)
- Dependency graph + ordered teardown plan
- Cost attribution per resource, and "still billing while stopped" detection
- Human approval via LangGraph interrupt
- Real stop / terminate / delete / release actions
- Verification of final state

### OUT — say these on the roadmap slide, don't build them

- Slack integration
- The CopilotKit web UI (demo from the terminal; see §5)
- RDS, NAT Gateways, load balancers, S3
- Multi-account / AWS Organizations
- Persistent storage of investigation history
- Bedrock AgentCore deployment

---

## 4. Three-day schedule

### Day 1 (5 Sep) — make the pipeline real

| Task | File | Est. |
|---|---|---|
| Wire real metrics into investigate | `graph/nodes/investigate.py` | 15 min |
| Make the CloudWatch window configurable (see §6 trap) | `tools/aws/metrics.py` | 15 min |
| Real AWS actions: stop, terminate, delete volume, release EIP, snapshot | `tools/aws/actions.py` | 1.5 h |
| Volumes + Elastic IPs + snapshots inventory | `tools/aws/volumes.py`, `addresses.py` | 1.5 h |
| "Is this still billing while stopped?" cost logic | `tools/aws/cost.py` | 1 h |
| GitHub evidence: last commit, branch exists, PR status | `tools/github/*.py` | 2 h |
| Conditional routing on the recommendation | `graph/routing.py` | 30 min |
| Real execute + verify | `graph/nodes/execute.py`, `verify.py` | 1 h |

**End of day 1: the graph runs against real AWS with zero mocked values.**

### Day 2 (6 Sep) — the differentiator, then freeze

| Task | File | Est. |
|---|---|---|
| Dependency graph discovery + topological teardown ordering | `policy/dependencies.py` (new) | 2.5 h |
| The PLAN node | `graph/nodes/plan.py` (new) | 1 h |
| Deterministic safety rules | `policy/safety.py` | 1 h |
| Approval as a real `interrupt()` | `graph/nodes/approval.py` | 1 h |
| Demo fixture: a deliberately messy stack (see §5.1) | `scripts/setup_demo_stack.py` | 1 h |
| Evaluation harness — the metrics in §7 | `tests/`, `scripts/evaluate.py` | 1.5 h |
| **Redact + pseudonymize before the LLM call** (§11.3) | `evidence/formatter.py` | 45 min |
| **Per-resource approval isolation** (§11.2) | `graph/nodes/approval.py` | 30 min |
| Judge-facing README rewrite | `README.md` | 45 min |

**Code freeze end of day 2.** Nothing ships on day 3 that isn't slides or video.

### Day 3 (7 Sep) — deliverables

| Task | Est. |
|---|---|
| 10-slide deck (§8) | 3 h |
| Rehearse the demo run end to end, twice | 1 h |
| Record and edit the 5-minute video (§9) | 2.5 h |
| Package and submit — one submission only, max 5 GB | 1 h |

---

## 5. The demo

### 5.1 Demo fixture — build this on day 2

A script that creates a deliberately messy, realistic footprint in the sandbox account:

- One **stopped** `t3.micro` tagged `Project=payments-poc`, `Environment=dev` — still billing EBS
- An **extra 8 GB volume** attached with `DeleteOnTermination=false` — the orphan trap
- An **unassociated Elastic IP** — billing for nothing
- An **old snapshot** from a deleted volume
- A **security group referenced by another SG** — forces correct teardown ordering
- One **running, genuinely busy** instance tagged `Environment=prod` — the agent must leave it alone

Cost: roughly $0.50/day. Safe against the $20 budget for three days. Tear it down after filming.

### 5.2 The demo narrative

1. "Here's a $20/month bill for a project that shipped in July and nobody has touched since."
2. Agent detects the stopped instance — **and points out that stopped ≠ free**.
3. Evidence: 1.4% CPU, no network, last commit 6 weeks ago, branch deleted, PR merged.
4. Verdict: retire, with a reason and a confidence score.
5. **The moment that sells it** — the ordered teardown plan appears: disassociate EIP → release EIP →
   snapshot volume → terminate instance → delete orphaned volume → delete SG. With a cost saved per line.
6. Human approves.
7. It executes in order, and verifies each step.
8. The prod instance is untouched, and the agent says why.

Point 5 is the whole pitch. Make it the centre of the video.

---

## 6. Traps

1. **The 7-day CloudWatch window.** `metrics.py` requests 7 days of history. A demo instance created
   on 5 Sep has 2 days at most, and may return zero datapoints — every metric shows `None`.
   **Make `days` a parameter and demo at 1–2 days.** Handle `None` in the prompt so the LLM doesn't
   reason over nulls.
2. **AWS keys expire every 12 hours.** They will die mid-recording. Refresh from the portal right
   before filming.
3. **$20 revokes account access, $30 terminates the account.** Check the budget bar every morning.
   Do not leave the demo stack running overnight.
4. **`assess.py` builds its Groq client at module import** — anything that imports the graph without
   `GROQ_API_KEY` set fails immediately. Fine locally, worth knowing if it's ever deployed.
5. **Termination is irreversible.** Never run the agent against anything but the sandbox account.
   Consider requiring an explicit `--allow-terminate` flag at the CLI.

---

## 7. Evaluation — needed for the deck (Session 3 grades this)

| Metric | How we measure it |
|---|---|
| Recommendation accuracy | A labelled set of ~10 resources (5 idle, 5 active). Report precision/recall on "retire". **Recall on 'keep' matters most — a false retire is the expensive error.** |
| Schema validation pass rate | % of `assess` calls returning a valid `Recommendation` first try |
| Tool-call success rate | % of boto3 calls returning a usable result |
| Teardown plan correctness | % of generated plans that execute without a dependency error |
| Cost identified vs. actual | Estimated monthly saving compared against the real reduction |
| Token cost per investigation | Summed across a run — a real number for the deck |

Ten labelled resources is enough. The point is showing a methodology, not a benchmark.

---

## 8. Deck outline (10 slides)

1. **Title & team**
2. **Problem** — "I stopped my instances. I was still charged." Lead with the personal story, then the AWS pricing evidence
3. **Solution overview** — detect → prove → plan the teardown → approve → execute
4. **Methodology** — the evidence model; why the LLM only ever sees evidence
5. **Technical architecture** — the LangGraph diagram, tools, safety layer
6. **Innovation** — two claims, both concrete: (a) evidence from *outside* AWS — GitHub tells us the
   project is dead, which no cost tool can know; (b) the dependency graph — *Cloud Custodian runs static
   YAML a human maintains; a fixed script cannot order a teardown it has never seen*
7. **Benefits** — $X/month found on a stack of N resources; minutes instead of an afternoon
8. **Demo preview** — the ordered teardown plan screenshot
9. **Roadmap** — Slack approvals, web UI, multi-account, RDS/NAT/ALB, AgentCore deployment
10. **Close**

Tie slide 6 to originality and slide 7 to benefits — those are two separate 20% blocks.

---

## 9. Video (5 minutes)

- 0:00 **Hook** — a real AWS bill for a project nobody uses
- 0:30 **Problem** — show that a *stopped* instance is still charging, then show the delete failing on a dependency error
- 1:00 **Solution** — one sentence, plus the pipeline diagram
- 1:30 **Demo** — the run from §5.2. Narrate the reasoning, not the UI
- 3:30 **Impact** — dollars found, time saved, the prod instance correctly left alone
- 4:15 **Close** — roadmap in one line

Show the agent *deciding*. Say out loud where it plans, where it acts, and where it adapts.

---

## 10. Honest risks

| Risk | Mitigation |
|---|---|
| 3 days, 4 mocked nodes, no deck | Freeze code end of day 2. Cut scope, not the deliverables |
| Dependency graph is the hardest piece and it's on day 2 | Ship a 4-resource-type version. It doesn't need to be general to be demonstrable |
| Real termination could go wrong on camera | Rehearse against a rebuilt fixture. Film the second run, not the first |
| The problem is B2B, not a heartstring use case | The rubric rewards productivity, cost and compliance benefits explicitly. Lead with the money and the personal story |
| No web UI | Judges grade "runs as demonstrated in the video". A clean terminal demo with real AWS calls beats a broken UI. Put it on the roadmap |
| Mature prior art exists (Cloud Custodian; and Cloud Janitor did a similar hackathon build) | Do not pretend otherwise — **name them on the innovation slide**. Finding a competitor sharpens a pitch; being caught unaware of one destroys it. Our answer is §2.4 |
| We built things we never surfaced (§11.5) | Anything not visible in the 5-minute demo does not exist. Wire before you build more |

---

## 11. Lessons from prior art — "Cloud Janitor"

A previous hackathon project (Kiro-built, ~500 commits, 1,295 tests, shipped to PyPI) solved a
neighbouring problem: multi-agent AWS cost + security auditing with Terraform remediation behind an
approval gate. It is far more mature than anything we will produce in three days, and reading it is
worth more than pretending it doesn't exist. What follows is what we take, what we skip, and why.

### 11.1 Their framing is better than ours — steal it

> "The scanning problem is basically solved industry-wide. Cost Explorer and Security Hub already tell
> you what's wrong. What nobody has built well is **the trust layer**: the moment a tool says here's
> the exact change, here's how to undo it, are you sure — and means it."

That is our pitch, stated better than we had it. It also settles an architectural question: the
approval gate is a **first-class state machine from day one**, not a UI afterthought. Our §2.3 already
leans this way; this confirms it.

They also named their competitor (Cloud Custodian) directly and explained the gap. **Do the same on
slide 6.** A judge who knows the space and hears no mention of Cloud Custodian assumes we didn't look.

### 11.2 Approval must be per-resource, not per-run — this is a real bug we would have shipped

Their post-mortem: *"Approving one resource's remediation could previously have silently applied
everything else sitting in the same generated Terraform file."*

Our design has exactly this hole. `ApprovalDecision` in `schemas.py` is a single verdict for the whole
run, so approving a teardown of instance A would authorise every action the plan contains.

**Fix on day 2:** approval is granted per resource ID, and `execute` filters the plan to only the
approved IDs. Their gate is also deliberately hostile — typed `APPROVE <resource-id>`, case-sensitive,
three failures locks it out. We should at minimum require typing the resource ID rather than "y",
because the action is irreversible.

### 11.3 We are shipping resource metadata to a third party and haven't thought about it

`assess.py` sends `resource.model_dump_json()` to Groq. That payload contains instance IDs, and tags
which routinely carry owner emails, project codenames, and cost centres. They hit this and shipped:

- a **redaction layer** applied before anything reaches a log or a screen — strips account IDs, ARNs,
  `AKIA*`/`ASIA*` keys, VPC and subnet IDs
- a **kill switch** (`JANITOR_AI_ENABLED=false`) for zero network egress
- **BYO LLM endpoint**

and listed *"pseudonymise resource names before they ever reach an LLM"* as future work they hadn't
done yet.

**We can ship that pseudonymisation in about 30 minutes**, and it fills `evidence/formatter.py`, which
is currently an empty file: map `i-0abc123` → `RES-1` before the prompt, keep the mapping in state, map
back after. The LLM reasons over shapes, not identifiers. It costs nothing, it is a genuine privacy
guarantee rather than a policy promise, and it is a strong, specific answer to "how did you think about
data governance?" — a question we would otherwise fumble.

### 11.4 Their bug list maps onto our code

| Their finding | Our equivalent |
|---|---|
| A clean account with zero findings was reported as a **pipeline failure** | `detect.py` sets `error` when no instances are found, and nothing routes on it. **An empty account is a valid, successful outcome** — say so, don't crash |
| Findings store resolved relative to the wrong directory | `scripts/test_groq_connection.py` uses a cwd-relative `load_dotenv("../.env")` while everything else resolves absolutely. Centralise on `config.py` |
| Rollback plan generated **before** execution, not after | Our snapshot-before-delete is the same instinct. Generalise it: emit a **restore recipe** — AMI, instance type, SGs, tags, snapshot IDs — as an artifact alongside the plan. Terminate is irreversible; the recipe is the only honest safety net |
| Subprocess inherited the full parent env, handing AWS + LLM keys to Terraform | We spawn no subprocesses, so this doesn't bite us. Worth remembering if we ever shell out |

### 11.5 The warning that applies to us most

> "Implementation completeness isn't integration completeness. We built a full second wave of agents,
> fully tested and working in isolation, and for most of the build, **not wired into the dashboard**.
> Getting powerful agents built is the easy 80%. Surfacing them somewhere a judge can click through in
> three minutes is the harder 20%."

We are already living this: `metrics.py` is written, tested, and **called by nothing**. The starter UI
is wired to a flight-search demo. **Anything not visible in the five-minute video does not exist.**
Wire what we have before writing anything new — this is the argument for the day-2 code freeze.

### 11.6 Testing — a realistic version of their standard

They ran 1,295 tests with no pass-by-default assertions and property-based testing via Hypothesis,
which surfaced a real bug in an exclusion filter. We cannot match that in three days and shouldn't try.

**What we can do, and what would genuinely impress:** one property test over the teardown ordering.
Generate random dependency graphs, assert the invariant *no resource is ever scheduled for deletion
before something that depends on it*. That is a handful of lines with Hypothesis, it tests the one
piece of logic where a bug is expensive, and it gives us a real answer to "how do you know the plan is
correct?" — far better than a row of `assert True`.

Also worth copying: they labelled unfinished work honestly ("GCP/Azure left as interface stubs rather
than faked"). Our empty modules should be labelled the same way in the README, not quietly implied to
work.

### 11.7 Considered and rejected for a 3-day build

| Their approach | Verdict |
|---|---|
| **LocalStack + Terraform** for a reproducible demo with no real AWS account | **Tempting** — it would solve our $20 budget, the 12-hour key expiry, and the risk of a live terminate failing on camera. But standing up LocalStack + seeding a stack is most of a day. **Cheap middle path (~15 min): add an `AWS_ENDPOINT_URL` override to `client.py`.** It costs almost nothing, and it means LocalStack is a config change later rather than a rewrite |
| **A dry-run mode that survives a judge's machine** (`TF_CMD=echo`) | **Adopt a version of this.** A `--dry-run` flag plus recorded AWS responses means the demo still runs when our keys expire mid-recording. Directly mitigates trap §6.2 |
| Terraform as the remediation engine | **Skip.** boto3 calls are more direct for our resource set, and Terraform can't manage resources it didn't create without an import step — a gap they flagged in their own roadmap |
| Their own **MCP server** (10 tools) | **Skip, but put it on the roadmap slide.** MCP was covered in the training, so naming it shows we understood the stack |
| Spec-driven workflow with auto-generated compliance docs | **Skip.** Valuable over 500 commits; pure overhead over three days |
| PyPI packaging with a real CLI entry point | **Skip.** Nice-to-have that judges won't check. `uv run` is fine |
| Security posture scanning (open ports, unencrypted volumes) | **Skip.** Doubling the scope halves the depth. Our story is cost and lifecycle, and it's sharper for staying narrow |

---

## 12. Code-level findings from the Cloud Janitor repo

Read at `/Users/hayden/Cloud-Janitor` — 129 Python files, ~9,600 LOC in `src/`. Six patterns worth
copying, ranked by value-for-effort in a 3-day build.

### 12.1 Swappable provider backend — *copy this first*

`mcp_server/backends/` holds `fixture_provider.py`, `aws_provider.py`, plus honestly-labelled GCP and
Azure stubs. The real one wires `AWS_ENDPOINT_URL` into every boto3 client, so the same code runs
against real AWS or LocalStack. **The demo runs on fixtures by default.**

Why this matters for us: our keys expire every 12 hours and *will* die mid-recording, our budget is
$20, and a live terminate can fail on camera. A provider switch means the demo never depends on any
of that.

**Our version (~1 hour):** add `AWS_ENDPOINT_URL` support to `tools/aws/client.py`, and a
`CLOUDCLEANER_PROVIDER=fixture|aws` env flag that swaps `inventory.py`/`metrics.py` for recorded JSON.
Record the fixtures from one real run so they're genuine AWS responses, not invented ones.

### 12.2 `ReasoningLogger` — best value-for-effort in the whole repo

`agents/reasoning_logger.py`, ~160 lines. A JSONL stream where every agent emits typed events:

```python
VALID_EVENT_TYPES = {"check", "finding", "skip", "decision", "handoff"}
logger.emit("finops_auditor", "check", "cache-prod-01", "Checking idle duration")
```

Truncated per run, rotates at 10 MB, and **never raises on a filesystem error** — logging must not
kill the agent.

This is three things at once: the explainability layer, the demo visual (a live reasoning trail
scrolling during the video), and our §7 evaluation metrics for free — tool-call success rate and loop
counts fall straight out of the log. Session 3 asks us to "show the reasoning a judge can follow";
this is literally that.

**Copy the shape almost verbatim into `evidence/collector.py`.** ~60 lines for us.

### 12.3 Their approval gate confirms our §11.2 fix, and goes further

`agents/approval_gate.py`, 522 lines. Three separate typed commands, all case-sensitive exact-match:

```
APPROVE <resource_id>
ROLLBACK <resource_id>
CONFIRM ROLLBACK <resource_id>     ← rollback is deliberately two-step
```

The parser rejects leading/trailing whitespace, a wrong prefix, an empty ID, and a mismatched ID.
Three failed attempts locks the gate.

**Take the shape, not the 522 lines.** For us: typing the resource ID is the approval — never `y/n` —
because our action is irreversible where theirs is a Terraform apply they can roll back.

### 12.4 Rollback is generated *before* execution, side by side with the plan

`remediation_architect.py` writes `rollbacks/<resource_id>.tf` at **plan** time, not after failure.
A resource with no generatable rollback doesn't proceed.

**Our version:** a **restore recipe** JSON emitted per resource at plan time — AMI ID, instance type,
security groups, tags, snapshot IDs, EIP allocation. Terminate is irreversible, so the recipe is the
only honest safety net we can offer. Emitting it before approval also makes the approval meaningful:
the human sees exactly what could and couldn't be undone.

### 12.5 Confirmed at code level: they *block*, we *order*

```python
if dep_report.has_dependencies:
    blocked = True
    recommendation = f"BLOCKED: {resource_id} has {n} dependent(s). Manual review required."
```

That's the whole dependency story — detect dependents, refuse, hand it back to a human. **The thing
that was hard for our teammate — working out what to delete first — is exactly where they stop.**

Our ordered teardown is therefore a real advance over the closest prior art, not a reframing. Say it
in those words on slide 6. Their `check_dependencies` is also fixture-backed; ours will walk the real
graph via `describe_*`.

### 12.6 Two smaller things

**A richer finding record.** Their finding carries `severity`, `cost_estimate_monthly`, `idle_days`,
`title`, `detected_at`, `agent`, `category`, `metadata`. Our `Recommendation` has only action, reason,
confidence — too thin to render a useful approval screen or to total up savings. Add `severity`,
`estimated_monthly_saving` and `evidence_summary`.

**Severity is deterministic Python, not an LLM call.** `classify_severity()` is a pure rule function.
This is the right split and it validates our `policy/` layer: **the model reasons, the rules
classify.** Rules are testable, cheap, and cannot be talked out of a verdict.

Also worth adopting: their `JANITOR_AI_ENABLED=false` kill switch. Ours would be
`CLOUDCLEANER_AI_ENABLED=false` — falls back to rules-only, no data leaves the machine. One env var,
and it's a strong answer to a data-governance question.

### 12.7 Revised task list

Fold into day 2, after the dependency graph:

| Task | File | Est. |
|---|---|---|
| `ReasoningLogger` | `evidence/collector.py` | 45 min |
| Fixture provider + `AWS_ENDPOINT_URL` | `tools/aws/client.py`, `fixtures/` | 1 h |
| Typed `APPROVE <resource-id>` parsing | `graph/nodes/approval.py` | 30 min |
| Restore recipe emitted at plan time | `graph/nodes/plan.py` | 45 min |
| `severity` + `estimated_monthly_saving` on the recommendation | `schemas.py`, `policy/risk.py` | 30 min |
| `CLOUDCLEANER_AI_ENABLED` kill switch | `config.py`, `graph/nodes/assess.py` | 15 min |
