import yaml

from cloudcleaner.tools.github.client import get_github_client
from github import GithubException


def get_last_workflow_run_at(repository) -> str | None:    
    workflow_runs = repository.get_workflow_runs()
    
    for run in workflow_runs:
        return run.created_at.isoformat()
    
    return None
    
def has_scheduled_workflow(repository) -> bool:
    try:
        workflow_files = repository.get_contents(".github/workflows")
    except GithubException as error:
        if error.status == 404:
            return False
        raise
        
    for workflow_file in workflow_files:
        if not workflow_file.name.endswith((".yml", ".yaml")):
            continue
            
        workflow_yaml = yaml.load(
            workflow_file.decoded_content,
            Loader=yaml.BaseLoader,
        )
        
        if not workflow_yaml:
            continue
            
        triggers = workflow_yaml.get("on")
        
        if isinstance(triggers, dict) and "schedule" in triggers:
            return True
            
    return False
    
def get_cicd_evidence(repo: str) -> dict | None:
    github = get_github_client()
    repository = github.get_repo(repo)
    
    last_workflow_run_at = get_last_workflow_run_at(repository)
    scheduled_workflow_exists = has_scheduled_workflow(repository)
    
    if last_workflow_run_at is None and not scheduled_workflow_exists:
        return None
        
    return {
        "last_workflow_run_at": last_workflow_run_at,
        "scheduled_workflow_exists": scheduled_workflow_exists,
    }
    