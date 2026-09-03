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
You are CloudCleaner, a cloud lifecycle investigation agent.

Based only on the evidence provided, recommend one of:

- keep
- investigate_more
- stop

Do not recommend deletion or termination.

Resource:
{resource.model_dump_json(indent=2)}

AWS evidence:
{aws.model_dump_json(indent=2)}

GitHub and CI/CD evidence:
{github.model_dump_json(indent=2)}

Explain the recommendation clearly.
"""

    structured_model = model.with_structured_output(
        Recommendation
    )

    recommendation = structured_model.invoke(prompt)

    return {
        "recommendation": recommendation,
    }