import sys
from pathlib import Path

parent_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(parent_dir))

from cloudcleaner.tools.github.branches import branch_exists


def main():
    repo = "nus-test/nus-test.github.io"
    
    existing_branch = "main"
    missing_branch = "this-branch-should-not-exist"
    
    print(
        f"Branch '{existing_branch}':",
        branch_exists(repo, existing_branch),
    )
    
    print(
        f"Branch '{missing_branch}':",
        branch_exists(repo, missing_branch),
    )
    

if __name__ == "__main__":
    main()
