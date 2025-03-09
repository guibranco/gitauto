from config import GITHUB_API_URL, TIMEOUT
from services.github.create_headers import create_headers
from utils.handle_exceptions import handle_exceptions
from security import safe_requests


@handle_exceptions(default_return_value=False, raise_on_error=False)
def check_user_is_collaborator(owner: str, repo: str, user: str, token: str) -> bool:
    """https://docs.github.com/en/rest/collaborators/collaborators?apiVersion=2022-11-28#check-if-a-user-is-a-repository-collaborator"""
    url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/collaborators/{user}"
    headers = create_headers(token=token)
    response = safe_requests.get(url=url, headers=headers, timeout=TIMEOUT)

    # Return False if 404 (user is not a collaborator)
    if response.status_code == 404:
        return False

    response.raise_for_status()
    return response.status_code == 204
