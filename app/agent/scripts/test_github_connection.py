import sys
from pathlib import Path

parent_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(parent_dir))

from cloudcleaner.tools.github.client import get_github_client


def main():
    github = get_github_client()
    
    user = github.get_user()
    
    print("GitHub connection successful")
    print("Username:", user.login)
    

if __name__ == "__main__":
    main()
    