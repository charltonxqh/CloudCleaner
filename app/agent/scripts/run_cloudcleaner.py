from cloudcleaner.graph.graph import graph


result = graph.invoke({})

print("\n=== CLOUDCLEANER ===")

print("\nResource:")
print(result["resource"])

print("\nAWS evidence:")
print(result["aws_evidence"])

print("\nGitHub evidence:")
print(result["github_evidence"])

print("\nRecommendation:")
print(result["recommendation"])

print("\nApproval:")
print(result["approval"])

print("\nExecution:")
print(result.get("execution_results", []))

print("\nVerification:")
print(result.get("verification_results", []))

print("\nRollback:")
print(result.get("rollback_results", []))