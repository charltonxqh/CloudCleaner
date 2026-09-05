from cloudcleaner.tools.github.branches import branch_exists
from cloudcleaner.tools.github.client import get_github_client


def get_latest_pr(repo: str):
    github = get_github_client()
    repository = github.get_repo(repo)
    
    pull_requests = repository.get_pulls(
        state="all",
        sort="updated",
        direction="desc",
    )
    
    for pr in pull_requests:
        return pr
    
    return None
    
def get_pr_status(pr) -> str:
    if pr.state == "open":
        return "open"
    
    if pr.merged:
        return "merged"
    
    return "closed"
    
def get_latest_pr_evidence(repo: str) -> dict | None:
    pr = get_latest_pr(repo)
    
    if pr is None:
        return None

    branch = pr.head.ref
    
    return {
        "pr_number": pr.number,
        "pr_status": get_pr_status(pr),
        "branch": branch,
	"branch_exists": branch_exists(repo, branch)
    }
    
