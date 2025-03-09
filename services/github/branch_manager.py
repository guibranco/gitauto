from config import GITHUB_API_URL, TIMEOUT
from services.github.create_headers import create_headers
from utils.handle_exceptions import handle_exceptions
from security import safe_requests


@handle_exceptions(default_return_value=("main", ""), raise_on_error=True)
def get_default_branch(owner: str, repo: str, token: str):
    # Get the default branch name first
    # https://docs.github.com/en/rest/repos/repos?apiVersion=2022-11-28#get-a-repository
    url = f"{GITHUB_API_URL}/repos/{owner}/{repo}"
    headers = create_headers(token=token)
    response = safe_requests.get(url=url, headers=headers, timeout=TIMEOUT)
    response.raise_for_status()
    data = response.json()
    default_branch_name: str = data["default_branch"]

    # Get the latest commit SHA for the default branch
    # https://docs.github.com/en/rest/branches/branches?apiVersion=2022-11-28#get-a-branch
    branch_url = f"{url}/branches/{default_branch_name}"
    branch_response = safe_requests.get(url=branch_url, headers=headers, timeout=TIMEOUT)
    branch_response.raise_for_status()
    branch_data = branch_response.json()
    latest_commit_sha: str = branch_data["commit"]["sha"]
    return default_branch_name, latest_commit_sha
