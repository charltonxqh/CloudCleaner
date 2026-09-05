import sys
from pathlib import Path

parent_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(parent_dir))

from cloudcleaner.tools.github.cicd import (
    get_cicd_evidence,
    get_last_workflow_run_at,
    has_scheduled_workflow,
)


def main():
    repo = "remarkablemark/github-actions-workflows"
    print("_Repo WITH SCHEDULED workflow(s)_")
        
    print("CI/CD evidence:", get_cicd_evidence(repo), "\n")
    
    repo = "nus-test/nus-test.github.io"
    print("_Repo WITHOUT SCHEDULED workflow(s)_")
    
    print("CI/CD evidence:", get_cicd_evidence(repo), "\n")
    
    repo = "wkxcass/CloudCleaner"
    print("_Repo WITHOUT workflows_")
        
    print("CI/CD evidence:", get_cicd_evidence(repo))
    

if __name__ == "__main__":
    main()
    