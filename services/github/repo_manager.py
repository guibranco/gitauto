# Third party imports

# Local imports
from config import GITHUB_API_URL, TIMEOUT
from services.github.create_headers import create_headers
from utils.handle_exceptions import handle_exceptions
from security import safe_requests


@handle_exceptions(default_return_value=False, raise_on_error=False)
def is_repo_forked(owner: str, repo: str, token: str):
    """https://docs.github.com/en/rest/repos/repos?apiVersion=2022-11-28#get-a-repository"""
    url = f"{GITHUB_API_URL}/repos/{owner}/{repo}"
    headers = create_headers(token=token)
    response = safe_requests.get(url=url, headers=headers, timeout=TIMEOUT)
    response.raise_for_status()
    is_fork: bool = response.json()["fork"]
    return is_fork
