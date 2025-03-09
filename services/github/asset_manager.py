from base64 import b64encode
from requests import post
from config import GITHUB_API_URL, TIMEOUT, UTF8
from services.github.create_headers import create_headers
from services.github.github_types import BaseArgs
from utils.handle_exceptions import handle_exceptions
from security import safe_requests


@handle_exceptions(default_return_value="", raise_on_error=False)
def get_base64(url: str) -> str:
    response = safe_requests.get(url=url, timeout=TIMEOUT)
    response.raise_for_status()
    base64_image: str = b64encode(response.content).decode(encoding=UTF8)
    return base64_image


@handle_exceptions(default_return_value="", raise_on_error=False)
def render_text(base_args: BaseArgs, text: str) -> str:
    """https://docs.github.com/en/rest/markdown/markdown?apiVersion=2022-11-28#render-a-markdown-document"""
    owner = base_args["owner"]
    repo = base_args["repo"]
    token = base_args["token"]
    url = f"{GITHUB_API_URL}/markdown"
    headers = create_headers(token=token)
    body = {"text": text, "mode": "gfm", "context": f"{owner}/{repo}"}
    response = post(url=url, headers=headers, json=body, timeout=TIMEOUT)
    response.raise_for_status()
    return response.text
