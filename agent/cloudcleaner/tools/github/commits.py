from cloudcleaner.tools.github.client import get_github_client


def get_latest_commit_at(repo: str) -> str | None:
    github = get_github_client()
    repository = github.get_repo(repo)
    
    commits = repository.get_commits()
    
    for commit in commits:
        return commit.commit.author.date.isoformat()
    
    return None
    
def get_latest_commit_evidence(repo: str) -> dict | None:
    commit_at = get_latest_commit_at(repo)
    
    if commit_at is None:
        return None
    
    return {
        "latest_commit_at": commit_at
    }
    