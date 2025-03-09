from json import dumps
import requests
from gql import gql
from config import TIMEOUT, PER_PAGE
from services.github.create_headers import create_headers
from services.github.github_manager import get_remote_file_content
from services.github.github_types import BaseArgs
from services.github.graphql_client import get_graphql_client
from utils.handle_exceptions import handle_exceptions
from security import safe_requests


@handle_exceptions(default_return_value=("", ""), raise_on_error=False)
def get_pull_request(url: str, token: str):
    """https://docs.github.com/en/rest/pulls/pulls?apiVersion=2022-11-28#get-a-pull-request"""
    headers = create_headers(token=token)
    res = safe_requests.get(url=url, headers=headers, timeout=TIMEOUT)
    res.raise_for_status()
    res_json = res.json()
    title: str = res_json["title"]
    body: str = res_json["body"]
    return title, body


@handle_exceptions(default_return_value=None, raise_on_error=False)
def get_pull_request_file_contents(url: str, base_args: BaseArgs):
    """https://docs.github.com/en/rest/pulls/pulls?apiVersion=2022-11-28#list-pull-requests-files"""
    token = base_args["token"]
    headers = create_headers(token=token)
    contents: list[str] = []
    page = 1
    while True:
        params = {"per_page": PER_PAGE, "page": page}
        response = safe_requests.get(
            url=url, headers=headers, params=params, timeout=TIMEOUT
        )
        response.raise_for_status()
        files = response.json()
        if not files:
            break
        for file in files:
            file_path = file["filename"]
            content = get_remote_file_content(file_path=file_path, base_args=base_args)
            contents.append(content)
        page += 1

    print(f"get_pull_request_file_contents: {dumps(obj=contents, indent=2)}")
    return contents


@handle_exceptions(default_return_value=None, raise_on_error=False)
def get_pull_request_file_changes(url: str, token: str):
    """url: https://api.github.com/repos/gitautoai/gitauto/pulls/517/files is expected.
    https://docs.github.com/en/rest/pulls/pulls?apiVersion=2022-11-28#list-pull-requests-files
    """
    headers = create_headers(token=token)
    changes: list[dict[str, str]] = []
    page = 1
    while True:
        params = {"per_page": PER_PAGE, "page": page}
        response = safe_requests.get(
            url=url, headers=headers, params=params, timeout=TIMEOUT
        )
        response.raise_for_status()
        files = response.json()
        if not files:
            break
        for file in files:
            if "patch" not in file:
                continue
            filename, status, patch = file["filename"], file["status"], file["patch"]
            changes.append({"filename": filename, "status": status, "patch": patch})
        page += 1
    return changes


@handle_exceptions(default_return_value=None, raise_on_error=False)
def update_pull_request_body(url: str, token: str, body: str):
    """https://docs.github.com/en/rest/pulls/pulls?apiVersion=2022-11-28#update-a-pull-request"""
    headers = create_headers(token=token)
    data = {"body": body}
    response = requests.patch(url=url, headers=headers, json=data, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


@handle_exceptions(default_return_value=None, raise_on_error=False)
def get_review_thread_comments(
    owner: str, repo: str, pull_number: int, comment_node_id: str, token: str
):
    """Get all comments in a review thread using GraphQL API
    https://docs.github.com/en/graphql/reference/objects#pullrequestreviewcomment
    """
    client = get_graphql_client(token)
    query = gql(
        """
        query GetReviewThreadComments($owner: String!, $repo: String!, $pull_number: Int!) {
          repository(owner: $owner, name: $repo) {
            pullRequest(number: $pull_number) {
              reviewThreads(first: 100) {
                nodes {
                  comments(first: 100) {
                    nodes {
                      id
                      author { login }
                      body
                      createdAt
                    }
                  }
                }
              }
            }
          }
        }
    """
    )

    variables = {
        "owner": owner,
        "repo": repo,
        "pull_number": pull_number,
    }

    result = client.execute(document=query, variable_values=variables)
    threads = (
        result.get("repository", {})
        .get("pullRequest", {})
        .get("reviewThreads", {})
        .get("nodes", [])
    )

    # Find the thread containing our comment
    for thread in threads:
        comments = thread.get("comments", {}).get("nodes", [])
        for comment in comments:
            if comment["id"] == comment_node_id:
                # print(f"get_review_thread_comments: {dumps(obj=comments, indent=2)}")
                return comments

    return []
