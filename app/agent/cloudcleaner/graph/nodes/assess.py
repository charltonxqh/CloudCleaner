from langchain_groq import ChatGroq

from cloudcleaner.config import GROQ_MODEL
from cloudcleaner.graph.state import CloudCleanerState
from cloudcleaner.schemas import Recommendation


model = ChatGroq(
    model=GROQ_MODEL,
    temperature=0,
)


def assess_node(state: CloudCleanerState):
    resource = state["resource"]
    aws = state["aws_evidence"]
    github = state["github_evidence"]

    prompt = f"""
You are CloudCleaner's cloud-resource assessment agent.

Your job is to assess whether a cloud resource should be:
- keep
- investigate_more
- stop

IMPORTANT RULES:
1. Use ONLY the evidence provided below.
2. Never invent or assume missing evidence.
3. A value of None means the evidence is unavailable.
4. If important evidence is unavailable, prefer "investigate_more".
5. Do not claim GitHub activity, branches, PRs, workflows, owners,
   deployments, or usage unless explicitly present in the evidence.
6. You are making a recommendation only. You are NOT authorizing
   or executing any action.

RESOURCE:
{resource.model_dump()}

AWS EVIDENCE:
{aws.model_dump()}

GITHUB EVIDENCE:
{github.model_dump()}

Return a recommendation based only on this evidence.
"""

    structured_model = model.with_structured_output(
        Recommendation
    )

    recommendation = structured_model.invoke(prompt)

    return {
        "recommendation": recommendation,
    }