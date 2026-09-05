import sys
from pathlib import Path

parent_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(parent_dir))

from cloudcleaner.tools.provider import get_github_evidence


def main():
    # Test 1: Repository with GitHub activity
    repo = "PyGithub/PyGithub"
    
    print(f"Testing GitHub evidence for: {repo}")
    evidence = get_github_evidence(repo)
    
    if evidence is None:
        print("No GitHub evidence returned.")
    else:
        print("GitHub evidence retrieved successfully:")
        print("  Repo:", evidence.repo)
        print("  Latest commit:", evidence.latest_commit_at)
        print("  PR number:", evidence.pr_number)
        print("  PR status:", evidence.pr_status)
        print("  Branch:", evidence.branch)
        print("  Branch exists:", evidence.branch_exists)
        print("  Last workflow run:", evidence.last_workflow_run_at)
        print("  Scheduled workflow:", evidence.scheduled_workflow_exists)
    
    # Test 2: Missing repository mapping
    
    print("\nTesting missing repository mapping:")
    no_repo_evidence = get_github_evidence(None)
    
    if no_repo_evidence is None:
        print("  No repo -> correctly returned None.")
    else:
        print("  Unexpected evidence:", no_repo_evidence)
    

if __name__ == "__main__":
    main()
    