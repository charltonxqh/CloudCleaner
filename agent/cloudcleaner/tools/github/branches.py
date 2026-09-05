from github import GithubException

from cloudcleaner.tools.github.client import get_github_client


def branch_exists(repo: str, branch: str) -> bool:
    github = get_github_client()
    repository = github.get_repo(repo)
    
    try:
        repository.get_branch(branch)
        return True
    except GithubException as exc:
        if exc.status == 404:
            return False
        raise
        