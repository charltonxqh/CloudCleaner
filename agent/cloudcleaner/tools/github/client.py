from github import Github

from cloudcleaner.config import GITHUB_TOKEN


def get_github_client():
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN is not set.")
        
    return Github(GITHUB_TOKEN)
    