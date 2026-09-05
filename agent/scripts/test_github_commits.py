import sys
from pathlib import Path

parent_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(parent_dir))

from cloudcleaner.tools.github.commits import get_latest_commit_evidence


def main():
    repo = "PyGithub/PyGithub"
    print("_Repo WITH commit(s)_")
    
    evidence = get_latest_commit_evidence(repo)
    
    if evidence is None:
        print("No commits found.")
        return
    
    print("Latest commit found at: ", evidence["latest_commit_at"])
    

if __name__ == "__main__":
    main()
    
