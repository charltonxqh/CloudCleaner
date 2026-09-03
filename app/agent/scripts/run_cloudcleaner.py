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

print("\nAction:")
print(result["action_result"])

print("\nVerification:")
print(result["verification_passed"])