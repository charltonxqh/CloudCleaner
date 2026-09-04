from cloudcleaner.graph.graph import graph


def main():
    result = graph.invoke({})

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

    recommendation = result.get("recommendation")

    if recommendation:
        print("Recommendation:")
        print(recommendation.model_dump())
        print()

    if result.get("error"):
        print("Error:")
        print(result["error"])


if __name__ == "__main__":
    main()