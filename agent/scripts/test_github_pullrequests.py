import sys
from pathlib import Path

parent_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(parent_dir))

from cloudcleaner.tools.github.pull_requests import get_latest_pr_evidence


def main():
    repo = "nus-test/nus-test.github.io"
    print("_Repo WITH PR(s)_")
    
    evidence = get_latest_pr_evidence(repo)
    
    if evidence is None:
        print("No pull requests found.")
        return
    
    print("Latest PR found")
    print("PR number:", evidence["pr_number"])
    print("PR status:", evidence["pr_status"])
    print("Branch:", evidence["branch"])
    print("Branch exists:", evidence["branch_exists"], "\n")

    repo = "wkxcass/CloudCleaner"
    print("_Repo WITHOUT PR(s)_")
    
    evidence = get_latest_pr_evidence(repo)
    
    if evidence is None:
        print("No pull requests found.")
        return
    
    print("Latest PR found")
    print("PR number:", evidence["pr_number"])
    print("PR status:", evidence["pr_status"])
    print("Branch:", evidence["branch"])
    print("Branch exists:", evidence["branch_exists"])
    

if __name__ == "__main__":
    main()
    
