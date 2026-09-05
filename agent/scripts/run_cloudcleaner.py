import uuid

from cloudcleaner.graph.graph import graph


def main():
    # The graph now carries a checkpointer so the approval node can interrupt,
    # which means every invoke needs a thread id.
    result = graph.invoke({}, {"configurable": {"thread_id": str(uuid.uuid4())}})

    print()
    print("=== CloudCleaner Result ===")
    print()

    resource = result.get("resource")
    if resource:
        print("Resource:")
        print(resource.model_dump())
        print()

    aws_evidence = result.get("aws_evidence")
    if aws_evidence:
        print("AWS Evidence:")
        print(aws_evidence.model_dump())
        print()

    github_evidence = result.get("github_evidence")
    if github_evidence:
        print("GitHub Evidence:")
        print(github_evidence.model_dump())
        print()

    recommendation = result.get("recommendation")
    if recommendation:
        print("Recommendation:")
        print(recommendation.model_dump())
        print()

    approval = result.get("approval")
    if approval:
        print("Approval:")
        print(approval.model_dump())
        print()

    execution_results = result.get("execution_results")
    if execution_results:
        print("Execution:")
        print(execution_results)
        print()

    verification_results = result.get("verification_results")
    if verification_results:
        print("Verification:")
        print(verification_results)
        print()

    rollback_results = result.get("rollback_results")
    if rollback_results:
        print("Rollback:")
        print(rollback_results)
        print()

    if result.get("error"):
        print("Error:")
        print(result["error"])


if __name__ == "__main__":
    main()
