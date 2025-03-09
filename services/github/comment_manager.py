from requests import delete, post
from config import GITHUB_API_URL, TIMEOUT, GITHUB_APP_USER_NAME
from constants.messages import COMPLETED_PR
from services.github.create_headers import create_headers
from services.github.github_types import BaseArgs
from utils.handle_exceptions import handle_exceptions
from utils.text_copy import UPDATE_COMMENT_FOR_422
from security import safe_requests


@handle_exceptions(default_return_value=None, raise_on_error=False)
def delete_a_comment(base_args: BaseArgs, comment_id: str):
    """https://docs.github.com/en/rest/issues/comments?apiVersion=2022-11-28#delete-an-issue-comment"""
    owner, repo, token = (base_args["owner"], base_args["repo"], base_args["token"])
    url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/issues/comments/{comment_id}"
    headers: dict[str, str] = create_headers(token=token)
    response = delete(url=url, headers=headers, timeout=TIMEOUT)
    response.raise_for_status()


@handle_exceptions(default_return_value=[], raise_on_error=False)
def get_all_comments(base_args: BaseArgs):
    """https://docs.github.com/en/rest/issues/comments?apiVersion=2022-11-28#list-issue-comments"""
    owner, repo, issue_number, token = (
        base_args["owner"],
        base_args["repo"],
        base_args["issue_number"],
        base_args["token"],
    )
    url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/issues/{issue_number}/comments"
    headers: dict[str, str] = create_headers(token=token)
    response = safe_requests.get(url=url, headers=headers, timeout=TIMEOUT)
    response.raise_for_status()
    comments: list[dict] = response.json()
    # print(f"All comments: {dumps(obj=comments, indent=2)}")
    return comments


@handle_exceptions(default_return_value=[], raise_on_error=False)
def filter_my_comments(comments: list[dict]):
    """Filter comments to only include those containing COMPLETED_PR and made by our GitHub app"""
    comments = comments or []
    return [
        comment
        for comment in comments
        if (
            COMPLETED_PR in comment["body"]
            or UPDATE_COMMENT_FOR_422 in comment["body"]
            or "▓" in comment["body"]
            or "░" in comment["body"]
        )
        and comment["user"]["login"] == GITHUB_APP_USER_NAME
    ]


@handle_exceptions(default_return_value=None, raise_on_error=False)
def delete_my_comments(base_args: BaseArgs):
    """Delete all comments made by GitAuto except the one with the checkbox"""
    comments = get_all_comments(base_args)
    my_comments = filter_my_comments(comments)
    # print(f"My comments: {dumps(obj=my_comments, indent=2)}")
    for comment in my_comments:
        delete_a_comment(base_args=base_args, comment_id=comment["id"])


@handle_exceptions(default_return_value=None, raise_on_error=False)
def reply_to_comment(base_args: BaseArgs, body: str):
    """https://docs.github.com/en/rest/pulls/comments?apiVersion=2022-11-28#create-a-reply-for-a-review-comment"""
    owner, repo, token = base_args["owner"], base_args["repo"], base_args["token"]
    pull_number = base_args["pull_number"]
    comment_id = base_args["review_id"]
    url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/pulls/{pull_number}/comments/{comment_id}/replies"
    headers: dict[str, str] = create_headers(token=token)
    response = post(url=url, headers=headers, json={"body": body}, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()["url"]
