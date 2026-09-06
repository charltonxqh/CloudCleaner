# CloudCleaner

**Finds AWS resources nobody is using, proves it, works out the order they have
to be dismantled in, and asks a human before touching anything.**

```bash
pip install cloudcleaner-agent
```

The command it installs is `cloudcleaner`.

---

## The problem

**Stopping an EC2 instance does not stop the bill.** Stop releases the compute
and nothing else — the root volume, any extra volumes, and the public IPv4
address all keep charging. A stopped `t3.micro` with a 16 GB volume and an
Elastic IP still costs about **$4.93 a month**, indefinitely.

**Deleting is a dependency puzzle.** You cannot release an Elastic IP while it
is associated. You cannot delete a volume while it is attached. Volumes created
with `DeleteOnTermination=false` outlive the instance and bill silently forever.
AWS reports exactly one blocker per attempt, so the order is discovered by trial
and error.

CloudCleaner does both parts: it finds the waste, and it works out the sequence.

---

## Try it without an AWS account

A demo account ships with the package, so nothing is read or changed:

```bash
CLOUDCLEANER_PROVIDER=fixture cloudcleaner scan
CLOUDCLEANER_PROVIDER=fixture cloudcleaner sweep
```

```
RESOURCE                   TYPE   STATE              $/MO
i-0999prod888              ec2    running          $34.37
vol-0orphan11              ebs    available         $8.00 *
i-0abc123def456789         ec2    stopped           $4.93 *
eipalloc-0unused9          eip    unassociated      $3.65 *

4 resources · $50.95/mo total · $16.58/mo not running but still billing (*)
```

## Against a real account

```bash
cloudcleaner doctor        # check credentials and configuration first
cloudcleaner scan
cloudcleaner investigate i-0abc123def456789
```

`CLOUDCLEANER_DRY_RUN` defaults to `true`. Nothing in AWS is modified until you
set it to `false`.

---

## What an investigation looks like

```
i-0abc123def456789  payments-poc  (ec2/stopped)  $4.93/mo
  -> retire (95%, high) Stopped 41 days with average CPU 0.4%, and still
     billing $4.93/mo for its volume and address.

     1. disassociate_address  eipassoc-0c1b2a3    $0.00  54.211.8.12 is attached
   ! 2. release_address       eipalloc-0f2e3d4    $3.65  public IPv4 bills hourly
     3. snapshot_volume       vol-0a9b8c7d6       $0.00  restore point first
   ! 4. terminate_instance    i-0abc123def456789  $4.93  idle instance
   ! 5. delete_volume         vol-0a9b8c7d6       $1.28  DeleteOnTermination=false

     3 of 5 steps cannot be undone                       $9.86/mo

  Type 'APPROVE i-0abc123def456789' to run this plan:
```

The order is computed, not scripted: dependencies are discovered at runtime and
topologically sorted, so a cycle raises rather than producing a sequence that
fails halfway.

---

## Commands

| | |
|---|---|
| `cloudcleaner scan` | what the account holds and what it costs |
| `cloudcleaner sweep` | investigate everything, approve nothing |
| `cloudcleaner investigate <id>` | one resource, with the approval prompt |
| `cloudcleaner history` | past runs, realised versus simulated savings |
| `cloudcleaner doctor` | check credentials and configuration |
| `cloudcleaner serve` | the HTTP API (needs the `[server]` extra) |

---

## Safety

Three independent gates stand between a verdict and a deletion:

1. **The model advises.** It sees only evidence and returns a typed verdict. It
   can be wrong, and a human can overrule it.
2. **The policy decides.** Plain Python — protected environments, protected
   tags, minimum age, risk score. No prompt reaches it, so it cannot be argued
   with or injected.
3. **A human commits.** You type the resource id exactly. Never `y/n`.

Every volume is snapshotted before deletion, a restore recipe is written before
anything runs, and dry-run savings are recorded as **simulated** — never as
money saved.

---

## Configuration

Read from `.env` in the working directory, upwards from it, or
`~/.cloudcleaner/.env`.

| Variable | Default | Effect |
|---|---|---|
| `GROQ_API_KEY` | — | required unless AI is disabled |
| `CLOUDCLEANER_PROVIDER` | `aws` | `fixture` runs offline against the demo account |
| `CLOUDCLEANER_DRY_RUN` | `true` | `false` actually modifies AWS |
| `CLOUDCLEANER_AI_ENABLED` | `true` | `false` uses the rules engine only; nothing leaves the machine |
| `CLOUDCLEANER_DATA_DIR` | `./output` or `~/.cloudcleaner` | where the database and logs are written |
| `AWS_ENDPOINT_URL` | — | point boto3 at LocalStack |
| `GITHUB_TOKEN` | — | optional; without it, code activity is skipped rather than failing |
| `METRIC_WINDOW_DAYS` | `7` | CloudWatch lookback |

## Extras

```bash
pip install cloudcleaner-agent              # the CLI
pip install 'cloudcleaner-agent[server]'    # plus the HTTP API and web frontend
pip install 'cloudcleaner-agent[all]'       # plus OpenAI, Anthropic, LangSmith
```

---

## Coverage

Eight resource types, each judged by the metric AWS actually publishes for it.
CPU is the EC2 signal and only the EC2 signal — a NAT gateway has no CPU, and
reading its absence as "idle" would be a confident recommendation to delete
something in use.

| Type | Idle signal | Why it is missed |
|---|---|---|
| EC2 instance | `CPUUtilization` | Stopping leaves storage and the IP billing |
| EBS volume | none published | Survives its instance when `DeleteOnTermination=false` |
| Elastic IP | association state | Billed hourly precisely *because* it is unused |
| Snapshot | age | No metrics at all; an AMI can pin it in place |
| NAT gateway | `BytesOutToDestination` | ~$32.85/mo, and it has no stopped state |
| Load balancer | `RequestCount` / `ActiveFlowCount` | Base rate charged with zero targets |
| RDS instance | `DatabaseConnections` | Stopped still bills storage — and AWS restarts it after 7 days |
| ElastiCache | `CurrConnections` | No stopped state; bills until deleted |

Alongside these: cost attribution and GitHub signals — last commit, branch
existence, PR status, CI runs — so the agent can tell whether the project that
owns a resource is still alive.

**Not yet:** EKS, multi-account, multi-region.

## Requirements

Python 3.12+. AWS credentials with read access plus whichever write permissions
you intend to use. A Groq API key, free at [console.groq.com](https://console.groq.com),
unless you run with `CLOUDCLEANER_AI_ENABLED=false`.

MIT licensed.
