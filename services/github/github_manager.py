# Standard imports
import base64
import datetime
import hashlib  # For HMAC (Hash-based Message Authentication Code) signatures
import hmac  # For HMAC (Hash-based Message Authentication Code) signatures
import json
import logging
import os
import time
from typing import Any

# Third-party imports
import jwt  # For generating JWTs (JSON Web Tokens)
import requests
from fastapi import Request

# Local imports
from config import (
    GITHUB_API_URL,
    GITHUB_API_VERSION,
    GITHUB_APP_ID,
    GITHUB_APP_IDS,
    GITHUB_PRIVATE_KEY,
    PRODUCT_NAME,
    PRODUCT_URL,
    TIMEOUT_IN_SECONDS,
    PRODUCT_ID,
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY,
    UTF8,
)
from services.github.github_types import (
    GitHubContentInfo,
    GitHubLabeledPayload,
    IssueInfo,
)
from services.openai.vision import describe_image
from services.supabase import SupabaseManager
from utils.file_manager import apply_patch, extract_file_name, run_command
from utils.handle_exceptions import handle_exceptions
from utils.text_copy import (
    UPDATE_COMMENT_FOR_RAISED_ERRORS_BODY,
    UPDATE_COMMENT_FOR_RAISED_ERRORS_NO_CHANGES_MADE,
    request_issue_comment,
    request_limit_reached,
)
from security import safe_requests


@handle_exceptions(default_return_value=None, raise_on_error=True)
def add_label_to_issue(
    owner: str, repo: str, issue_number: int, label: str, token: str
) -> None:
    """If the label doesn't exist, it will be created. Color will be automatically assigned. If the issue already has the label, no change will be made and no error will be raised. https://docs.github.com/en/rest/issues/labels?apiVersion=2022-11-28#add-labels-to-an-issue"""
    response: requests.Response = requests.post(
        url=f"{GITHUB_API_URL}/repos/{owner}/{repo}/issues/{issue_number}/labels",
        headers=create_headers(token=token),
        json={"labels": [label]},
        timeout=TIMEOUT_IN_SECONDS,
    )
    response.raise_for_status()


@handle_exceptions(default_return_value=None, raise_on_error=False)
def add_reaction_to_issue(
    owner: str, repo: str, issue_number: int, content: str, token: str
) -> None:
    """https://docs.github.com/en/rest/reactions/reactions?apiVersion=2022-11-28#create-reaction-for-an-issue"""
    response: requests.Response = requests.post(
        url=f"{GITHUB_API_URL}/repos/{owner}/{repo}/issues/{issue_number}/reactions",
        headers=create_headers(token=token),
        json={"content": content},
        timeout=TIMEOUT_IN_SECONDS,
    )
    response.raise_for_status()
    response.json()


@handle_exceptions(default_return_value=None, raise_on_error=False)
def commit_multiple_changes_to_remote_branch(
    diffs: list[str],
    new_branch: str,
    owner: str,
    repo: str,
    token: str,
) -> None:
    """Called from assistants api to commit multiple changes to a new branch."""
    for diff in diffs:
        file_path: str = extract_file_name(diff_text=diff)
        print(
            f"{time.strftime('%H:%M:%S', time.localtime())} File path: {file_path}.\n"
        )
        commit_changes_to_remote_branch(
            branch=new_branch,
            commit_message=f"Update {file_path}",
            diff_text=diff,
            file_path=file_path,
            owner=owner,
            repo=repo,
            token=token,
        )
        print(
            f"{time.strftime('%H:%M:%S', time.localtime())} Changes committed to https://github.com/{owner}/{repo}/tree/{new_branch}.\n"
        )


@handle_exceptions(default_return_value=None, raise_on_error=False)
def commit_changes_to_remote_branch(
    branch: str,
    commit_message: str,
    diff_text: str,
    file_path: str,
    owner: str,
    repo: str,
    token: str,
) -> None:
    """https://docs.github.com/en/rest/repos/contents#create-or-update-file-contents"""
    url: str = f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/{file_path}"

    # Get the SHA of the file if it exists
    response = safe_requests.get(
        url=url, headers=create_headers(token=token), timeout=TIMEOUT_IN_SECONDS
    )
    original_text = ""
    sha = ""
    print(f"{response.status_code=}\n")
    if response.status_code == 200:
        file_info: GitHubContentInfo = response.json()
        content: str = file_info.get("content")
        # content is base64 encoded by default in GitHub API
        original_text: str = base64.b64decode(s=content).decode(
            encoding=UTF8, errors="replace"
        )
        sha: str = file_info["sha"]
    elif response.status_code != 404:  # Error other than 'file not found'
        response.raise_for_status()

    # Create a new commit
    modified_text: str = apply_patch(original_text=original_text, diff_text=diff_text)
    if modified_text == "":
        return
    data: dict[str, str | None] = {
        "message": commit_message,
        "content": base64.b64encode(s=modified_text.encode(encoding=UTF8)).decode(
            encoding=UTF8
        ),
        "branch": branch,
    }
    if sha != "":
        data["sha"] = sha
    put_response = requests.put(
        url=url,
        json=data,
        headers=create_headers(token=token),
        timeout=TIMEOUT_IN_SECONDS,
    )
    put_response.raise_for_status()


@handle_exceptions(default_return_value=None, raise_on_error=False)
def create_comment(
    owner: str, repo: str, issue_number: int, body: str, token: str
) -> str:
    """https://docs.github.com/en/rest/issues/comments?apiVersion=2022-11-28#create-an-issue-comment"""
    response: requests.Response = requests.post(
        url=f"{GITHUB_API_URL}/repos/{owner}/{repo}/issues/{issue_number}/comments",
        headers=create_headers(token=token),
        json={
            "body": body,
        },
        timeout=TIMEOUT_IN_SECONDS,
    )

    response.raise_for_status()
    return response.json()["url"]


@handle_exceptions(default_return_value=None, raise_on_error=False)
def create_comment_on_issue_with_gitauto_button(payload: GitHubLabeledPayload) -> None:
    """https://docs.github.com/en/rest/issues/comments?apiVersion=2022-11-28#create-an-issue-comment"""
    installation_id: int = payload["installation"]["id"]
    token: str = get_installation_access_token(installation_id=installation_id)

    owner: str = payload["repository"]["owner"]["login"]
    owner_id: int = payload["repository"]["owner"]["id"]
    repo_name: str = payload["repository"]["name"]
    issue_number: int = payload["issue"]["number"]
    user_id: int = payload["sender"]["id"]
    user_name: str = payload["sender"]["login"]

    supabase_manager = SupabaseManager(url=SUPABASE_URL, key=SUPABASE_SERVICE_ROLE_KEY)

    # Proper issue generation comment, create user if not exist (first issue in an orgnanization)
    first_issue = False
    if not supabase_manager.user_exists(user_id=user_id):
        supabase_manager.create_user(
            user_id=user_id,
            user_name=user_name,
            installation_id=installation_id,
        )
        first_issue = True
    elif supabase_manager.is_users_first_issue(
        user_id=user_id, installation_id=installation_id
    ):
        first_issue = True

    requests_left, request_count, end_date = (
        supabase_manager.get_how_many_requests_left_and_cycle(
            user_id=user_id,
            installation_id=installation_id,
            user_name=user_name,
            owner_id=owner_id,
            owner_name=owner,
        )
    )

    body = "Click the checkbox below to generate a PR!\n- [ ] Generate PR"
    if PRODUCT_ID != "gitauto":
        body += " - " + PRODUCT_ID

    if end_date != datetime.datetime(
        year=1, month=1, day=1, hour=0, minute=0, second=0
    ):
        body += request_issue_comment(requests_left=requests_left, end_date=end_date)

    if requests_left <= 0:
        logging.info("\nRequest limit reached for user %s.", user_name)
        body = request_limit_reached(
            user_name=user_name,
            request_count=request_count,
            end_date=end_date,
        )

    if first_issue:
        body = "Welcome to GitAuto! 🎉\n" + body
        supabase_manager.set_user_first_issue_to_false(
            user_id=user_id, installation_id=installation_id
        )

    response: requests.Response = requests.post(
        url=f"{GITHUB_API_URL}/repos/{owner}/{repo_name}/issues/{issue_number}/comments",
        headers=create_headers(token=token),
        json={
            "body": body,
        },
        timeout=TIMEOUT_IN_SECONDS,
    )
    response.raise_for_status()

    return response.json()


def create_headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }


def create_jwt() -> str:
    """Generate a JWT (JSON Web Token) for GitHub App authentication"""
    now = int(time.time())
    payload: dict[str, int | str] = {
        "iat": now,  # Issued at time
        "exp": now + 600,  # JWT expires in 10 minutes
        "iss": GITHUB_APP_ID,  # Issuer
    }
    # The reason we use RS256 is that GitHub requires it for JWTs
    return jwt.encode(payload=payload, key=GITHUB_PRIVATE_KEY, algorithm="RS256")


@handle_exceptions(default_return_value=None, raise_on_error=False)
def create_pull_request(
    base: str,  # The branch name you want to merge your changes into. ex) 'main'
    body: str,
    head: str,  # The branch name that contains your changes
    owner: str,
    repo: str,
    title: str,
    token: str,
) -> str | None:
    """https://docs.github.com/en/rest/pulls/pulls#create-a-pull-request"""
    response: requests.Response = requests.post(
        url=f"{GITHUB_API_URL}/repos/{owner}/{repo}/pulls",
        headers=create_headers(token=token),
        json={"title": title, "body": body, "head": head, "base": base},
        timeout=TIMEOUT_IN_SECONDS,
    )
    response.raise_for_status()
    return response.json()["html_url"]


def create_remote_branch(
    branch_name: str,
    owner: str,
    repo: str,
    sha: str,
    comment_url: str,
    token: str,
) -> None:
    try:
        response: requests.Response = requests.post(
            url=f"{GITHUB_API_URL}/repos/{owner}/{repo}/git/refs",
            headers=create_headers(token=token),
            json={"ref": f"refs/heads/{branch_name}", "sha": sha},
            timeout=TIMEOUT_IN_SECONDS,
        )
        response.raise_for_status()
    except Exception as e:  # pylint: disable=broad-except
        update_comment_for_raised_errors(
            error=e,
            comment_url=comment_url,
            token=token,
            which_function=create_remote_branch.__name__,
        )


def initialize_repo(repo_path: str, remote_url: str) -> None:
    """Push an initial empty commit to the remote repository to create a commit sha."""
    if not os.path.exists(path=repo_path):
        os.makedirs(name=repo_path)

    run_command(command="git init", cwd=repo_path)
    with open(file=os.path.join(repo_path, "README.md"), mode="w", encoding=UTF8) as f:
        f.write(f"# Initial commit by [{PRODUCT_NAME}]({PRODUCT_URL})\n")
    run_command(command="git add README.md", cwd=repo_path)
    run_command(command='git commit -m "Initial commit"', cwd=repo_path)
    run_command(command=f"git remote add origin {remote_url}", cwd=repo_path)
    run_command(command="git push -u origin main", cwd=repo_path)


@handle_exceptions(default_return_value=None, raise_on_error=False)
def get_installation_access_token(installation_id: int) -> str | None:
    """https://docs.github.com/en/rest/apps/apps?apiVersion=2022-11-28#create-an-installation-access-token-for-an-app"""
    jwt_token: str = create_jwt()
    response: requests.Response = requests.post(
        url=f"{GITHUB_API_URL}/app/installations/{installation_id}/access_tokens",
        headers=create_headers(token=jwt_token),
        timeout=TIMEOUT_IN_SECONDS,
    )
    response.raise_for_status()
    return response.json()["token"]


@handle_exceptions(default_return_value=[], raise_on_error=False)
def get_installed_owners_and_repos(token: str) -> list[dict[str, int | str]]:
    """https://docs.github.com/en/rest/apps/installations?apiVersion=2022-11-28#list-repositories-accessible-to-the-app-installation"""
    owners_repos = []
    page = 1
    while True:
        response: requests.Response = safe_requests.get(
            url=f"{GITHUB_API_URL}/installation/repositories",
            headers=create_headers(token=token),
            params={"per_page": 100, "page": page},
            timeout=TIMEOUT_IN_SECONDS,
        )
        response.raise_for_status()
        repos = response.json().get("repositories", [])

        # If there are no more repositories, break the loop. Otherwise, add them to the list
        if not repos:
            break
        items: list[dict[str, int | str]] = [
            {
                "owner_id": repo["owner"]["id"],
                "owner": repo["owner"]["login"],
                "repo": repo["name"],
            }
            for repo in repos
        ]
        owners_repos.extend(items)

        # https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api?apiVersion=2022-11-28
        print("response.links:", json.dumps(response.links, indent=2))
        if "next" not in response.links:
            break
        page += 1
    return owners_repos


@handle_exceptions(default_return_value=[], raise_on_error=False)
def get_issue_comments(
    owner: str, repo: str, issue_number: int, token: str
) -> list[str]:
    """https://docs.github.com/en/rest/issues/comments#list-issue-comments"""
    response = safe_requests.get(
        url=f"{GITHUB_API_URL}/repos/{owner}/{repo}/issues/{issue_number}/comments",
        headers=create_headers(token=token),
        timeout=TIMEOUT_IN_SECONDS,
    )
    response.raise_for_status()
    comments: list[Any] = response.json()
    filtered_comments: list[Any] = [
        comment
        for comment in comments
        if comment.get("performed_via_github_app")
        and comment["performed_via_github_app"].get("id") not in GITHUB_APP_IDS
    ]
    print(f"\nIssue comments: {json.dumps(filtered_comments, indent=2)}\n")
    comment_texts: list[str] = [comment["body"] for comment in filtered_comments]
    return comment_texts


def get_latest_remote_commit_sha(
    owner: str,
    repo: str,
    branch: str,
    comment_url: str,
    unique_issue_id: str,
    clone_url: str,
    token: str,
) -> str:
    """SHA stands for Secure Hash Algorithm. It's a unique identifier for a commit.
    https://docs.github.com/en/rest/git/refs?apiVersion=2022-11-28#get-a-reference"""
    try:
        response: requests.Response = safe_requests.get(
            url=f"{GITHUB_API_URL}/repos/{owner}/{repo}/git/ref/heads/{branch}",
            headers=create_headers(token=token),
            timeout=TIMEOUT_IN_SECONDS,
        )
        response.raise_for_status()
        return response.json()["object"]["sha"]
    except requests.exceptions.HTTPError as e:
        if (
            e.response.status_code == 409
            and e.response.json()["message"] == "Git Repository is empty."
        ):
            logging.info(
                msg="Repository is empty. So, creating an initial empty commit."
            )
            initialize_repo(repo_path=f"/tmp/repo/{owner}-{repo}", remote_url=clone_url)
            return get_latest_remote_commit_sha(
                owner=owner,
                repo=repo,
                branch=branch,
                comment_url=comment_url,
                unique_issue_id=unique_issue_id,
                clone_url=clone_url,
                token=token,
            )
        raise
    except Exception as e:
        update_comment_for_raised_errors(
            error=e,
            comment_url=comment_url,
            token=token,
            which_function=get_latest_remote_commit_sha.__name__,
        )
        # Raise an error because we can't continue without the latest commit SHA
        raise RuntimeError(
            f"Error: Could not get the latest commit SHA in {get_latest_remote_commit_sha.__name__}"
        ) from e


@handle_exceptions(default_return_value=None, raise_on_error=False)
def get_oldest_unassigned_open_issue(
    owner: str, repo: str, token: str
) -> IssueInfo | None:
    """Get an oldest unassigned open issue without "gitauto" label in a repository. https://docs.github.com/en/rest/issues/issues?apiVersion=2022-11-28#list-repository-issues"""
    page = 1
    while True:
        response: requests.Response = safe_requests.get(
            url=f"{GITHUB_API_URL}/repos/{owner}/{repo}/issues",
            headers=create_headers(token=token),
            params={
                "assignee": "none",  # none, *, or username
                "direction": "asc",  # asc or desc
                "page": page,
                "per_page": 100,
                "sort": "created",  # created, updated, comments
                "state": "open",  # open, closed, or all
            },
            timeout=TIMEOUT_IN_SECONDS,
        )
        response.raise_for_status()
        issues: list[IssueInfo] = response.json()

        # If there are no corresponding issues, return None
        if not issues:
            return None

        # Find the first issue without the PRODUCT_ID label
        for issue in issues:
            if all(label["name"] != PRODUCT_ID for label in issue["labels"]):
                return issue

        # If there are open issues, but all of them have the PRODUCT_ID label, continue to the next page
        page += 1


@handle_exceptions(default_return_value=None, raise_on_error=False)
def get_owner_name(owner_id: int, token: str) -> str | None:
    """https://docs.github.com/en/rest/users/users?apiVersion=2022-11-28#get-a-user-using-their-id"""
    response: requests.Response = safe_requests.get(
        url=f"{GITHUB_API_URL}/user/{owner_id}",
        headers=create_headers(token=token),
        timeout=TIMEOUT_IN_SECONDS,
    )
    response.raise_for_status()
    return response.json()["login"]


@handle_exceptions(default_return_value="", raise_on_error=False)
def get_remote_file_content(
    file_path: str,  # Ex) 'src/main.py'
    owner: str,
    ref: str,  # Ex) 'main'
    repo: str,
    token: str,
) -> str:
    """https://docs.github.com/en/rest/repos/contents?apiVersion=2022-11-28"""
    url: str = f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/{file_path}?ref={ref}"
    headers: dict[str, str] = create_headers(token=token)
    response: requests.Response = safe_requests.get(
        url=url, headers=headers, timeout=TIMEOUT_IN_SECONDS
    )
    response.raise_for_status()
    encoded_content: str = response.json()["content"]  # Base64 encoded content

    # If encoded_content is image, describe the image content in text by vision API
    if file_path.endswith((".png", ".jpeg", ".jpg", ".webp", ".gif")):
        return describe_image(base64_image=encoded_content)

    # Otherwise, decode the content
    decoded_content: str = base64.b64decode(s=encoded_content).decode(encoding=UTF8)
    return decoded_content


def get_remote_file_tree(
    owner: str, repo: str, ref: str, comment_url: str, token: str
) -> list[str]:
    """
    Get the file tree of a GitHub repository at a ref branch.
    https://docs.github.com/en/rest/git/trees?apiVersion=2022-11-28#get-a-tree
    """
    response: requests.Response | None = None  # Otherwise response could be Unbound
    try:
        response = safe_requests.get(
            url=f"{GITHUB_API_URL}/repos/{owner}/{repo}/git/trees/{ref}?recursive=1",
            headers=create_headers(token=token),
            timeout=TIMEOUT_IN_SECONDS,
        )
        response.raise_for_status()
        return [item["path"] for item in response.json()["tree"]]
    except requests.exceptions.HTTPError as http_err:
        # Log the error if it's not a 409 error (empty repository)
        if http_err.response.status_code != 409:
            logging.error(
                msg=f"get_remote_file_tree HTTP Error: {http_err.response.status_code} - {http_err.response.text}"
            )
        return []
    except Exception as e:  # pylint: disable=broad-except
        update_comment_for_raised_errors(
            error=e,
            comment_url=comment_url,
            token=token,
            which_function=get_remote_file_tree.__name__,
        )
        return []


@handle_exceptions(raise_on_error=True)
async def verify_webhook_signature(request: Request, secret: str) -> None:
    """Verify the webhook signature for security"""
    signature: str | None = request.headers.get("X-Hub-Signature-256")
    if signature is None:
        raise ValueError("Missing webhook signature")
    body: bytes = await request.body()

    # Compare the computed signature with the one in the headers
    hmac_key: bytes = secret.encode()
    hmac_signature: str = hmac.new(
        key=hmac_key, msg=body, digestmod=hashlib.sha256
    ).hexdigest()
    expected_signature: str = "sha256=" + hmac_signature
    if not hmac.compare_digest(signature, expected_signature):
        raise ValueError("Invalid webhook signature")


@handle_exceptions(default_return_value=None, raise_on_error=False)
def update_comment(comment_url: str, body: str, token: str) -> dict[str, Any]:
    """https://docs.github.com/en/rest/issues/comments#update-an-issue-comment"""
    response: requests.Response = requests.patch(
        url=comment_url,
        headers=create_headers(token=token),
        json={"body": body},
        timeout=TIMEOUT_IN_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def update_comment_for_raised_errors(
    error: Any, comment_url: str, token: str, which_function: str
) -> dict[str, Any]:
    """Update the comment on issue with an error message and raise the error."""
    body = UPDATE_COMMENT_FOR_RAISED_ERRORS_BODY
    try:
        if isinstance(error, requests.exceptions.HTTPError):
            logging.error(
                "%s HTTP Error: %s - %s",
                which_function,
                error.response.status_code,
                error.response.text,
            )
            if (
                error.response.status_code == 422
                and error["message"]
                and error.message == "Validation Failed"
                and (
                    (
                        isinstance(error.errors[0], list)
                        and hasattr(error.errors[0][0], "message")
                        and error.errors[0][0].message.find(
                            "No commits between main and"
                        )
                        != -1
                    )
                    or (
                        not isinstance(error.errors[0], list)
                        and hasattr(error.errors[0], "message")
                        and error.errors[0].message.find("No commits between main and")
                        != -1
                    )
                )
            ):
                body = UPDATE_COMMENT_FOR_RAISED_ERRORS_NO_CHANGES_MADE
            else:
                logging.error(
                    "%s HTTP Error: %s - %s",
                    which_function,
                    error.response.status_code,
                    error.response.text,
                )
        else:
            logging.error("%s Error: %s", which_function, error)
    except Exception as e:  # pylint: disable=broad-except
        logging.error("%s Error: %s", which_function, e)
    update_comment(comment_url=comment_url, token=token, body=body)

    raise RuntimeError("Error occurred")
