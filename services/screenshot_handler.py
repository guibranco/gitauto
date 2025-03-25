# Standard library imports
from json import dumps
import os
import shutil
from time import sleep, time
from typing import Any
from urllib.parse import urlparse, quote

# Third-party imports
import boto3
from playwright.async_api import async_playwright

# Local imports
from config import GITHUB_APP_USER_NAME
from services.git.git_manager import (
    clone_repo,
    fetch_branch,
    get_current_branch,
    start_local_server,
    switch_to_branch,
)
from services.github.comment_manager import delete_a_comment, get_all_comments
from services.github.github_manager import create_comment, get_installation_access_token
from services.github.pulls_manager import get_pull_request_file_changes
from utils.handle_exceptions import handle_exceptions


@handle_exceptions(raise_on_error=True)
def get_url_filename(url_or_path: str) -> str:
    if url_or_path.startswith(("http://", "https://")):
        url_obj = urlparse(url_or_path)
        # Extract just the path part, removing the domain
        path = url_obj.path.lstrip("/")
    else:
        # For paths without domain, just use the path as is
        path = url_or_path.lstrip("/")

    # If path is empty, use "index" instead
    if not path:
        path = "index"

    return f"{quote(path)}.png"


@handle_exceptions(default_return_value=None, raise_on_error=False)
async def capture_screenshots(urls: list[str], output_dir: str) -> None:
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            args=[
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-gpu",
                "--single-process",
            ]
        )
        context = await browser.new_context()
        page = await context.new_page()
        viewport_size = {"width": 1512, "height": 982}
        await page.set_viewport_size(viewport_size)
        print(f"\nOpened browser and set viewport size to `{viewport_size}`")

        for url in urls:
            file_name = get_url_filename(url)
            file_path = os.path.join(output_dir, file_name)

            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(10000)
            await page.screenshot(path=file_path, full_page=True)
            print(f"\nCaptured screenshot for `{url}`")
            print(f"Saved screenshot to `{file_path}`")

        await browser.close()
        print("Closed browser")


@handle_exceptions(raise_on_error=True)
def upload_to_s3(file_path: str, s3_key: str) -> str:
    # S3 and IAM access policies are attached to the Lambda Function role so we don't need to specify AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and AWS_REGION
    # https://us-east-1.console.aws.amazon.com/iam/home?region=us-west-1#/roles/details/pr-agent-prod-role-5hjanfe3?section=permissions
    s3_client = boto3.client("s3")
    aws_s3_bucket_name = os.getenv("AWS_S3_BUCKET_NAME")
    if aws_s3_bucket_name is None:
        raise ValueError("AWS_S3_BUCKET_NAME is not set")
    aws_region = "us-west-1"
    extra_args = {"ContentType": "image/png"}
    s3_client.upload_file(file_path, aws_s3_bucket_name, s3_key, ExtraArgs=extra_args)
    print(f"Uploaded to S3: {quote(s3_key)}")
    return f"https://{aws_s3_bucket_name}.s3.{aws_region}.amazonaws.com/{quote(s3_key)}"


@handle_exceptions(raise_on_error=True)
def find_all_html_pages(repo_dir: str) -> list[str]:
    all_paths = set()

    for root, _, files in os.walk(repo_dir):
        for file in files:
            if file.endswith((".html", ".tsx", ".jsx")):
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, repo_dir)

                # Handle HTML files
                if file.endswith(".html"):
                    path = "/" + rel_path.replace("index.html", "").rstrip("/")
                    all_paths.add(path or "/")
                    print(f"Found HTML file: `{file_path}`")

                # Handle Next.js App Router
                elif "app/" in rel_path and file.endswith((".tsx", ".jsx")):
                    path = (
                        rel_path.rsplit("app/", maxsplit=1)[-1]
                        .replace("/page.tsx", "")
                        .replace("/page.jsx", "")
                        .replace("/layout.tsx", "")
                        .replace("/layout.jsx", "")
                    )
                    all_paths.add("/" + path.rstrip("/"))
                    print(f"Found Next.js App Router file: `{file_path}`")

                # Handle Next.js Pages Router
                elif "pages/" in rel_path and file.endswith((".tsx", ".jsx")):
                    path = (
                        rel_path.rsplit("pages/", maxsplit=1)[-1]
                        .replace("index.tsx", "")
                        .replace("index.jsx", "")
                        .replace(".tsx", "")
                        .replace(".jsx", "")
                    )
                    all_paths.add("/" + path.rstrip("/"))
                    print(f"Found Next.js Pages Router file: `{file_path}`")

    return list(all_paths)


@handle_exceptions(raise_on_error=True)
def get_target_paths(file_changes: list[dict[str, str]], repo_dir: str = None):
    has_css_changes = any(
        change.get("filename", "").endswith((".css", ".scss", ".sass", ".less"))
        for change in file_changes
    )

    # If there are any CSS changes, scan all pages in the repository
    if has_css_changes and repo_dir:
        return find_all_html_pages(repo_dir)

    changed_paths: set[str] = set()
    for i, change in enumerate(file_changes):
        print(f"Processing {i + 1} of {len(file_changes)}")
        file_path = change.get("filename", "")
        print(f"Processing file: {file_path}")

        # HTML files - direct path conversion
        if file_path.endswith(".html"):
            path = "/" + file_path.replace("index.html", "").rstrip("/")
            changed_paths.add(path or "/")
            print(f"Found HTML file: {file_path}")
            print(f"Affected path: {path}")

        # Next.js App Router
        elif "app/" in file_path and file_path.endswith((".tsx", ".jsx")):
            path = (
                file_path.split("app/")[-1]
                .replace("/page.tsx", "")
                .replace("/page.jsx", "")
                .replace("/layout.tsx", "")
                .replace("/layout.jsx", "")
            )
            changed_paths.add("/" + path.rstrip("/"))
            print(f"Found Next.js App Router file: {file_path}")
            print(f"Affected path: {path}")

        # Next.js Pages Router
        elif "pages/" in file_path and file_path.endswith((".tsx", ".jsx")):
            path = (
                file_path.split("pages/")[-1]
                .replace("index.tsx", "")
                .replace("index.jsx", "")
                .replace(".tsx", "")
                .replace(".jsx", "")
            )
            changed_paths.add("/" + path.rstrip("/"))
            print(f"Found Next.js Pages Router file: {file_path}")
            print(f"Affected path: {path}")

        # React components that might affect multiple pages
        # elif file_path.endswith((".tsx", ".jsx")) and (
        #     "components/" in file_path or "layouts/" in file_path
        # ):

    return list(changed_paths)


@handle_exceptions(raise_on_error=True)
async def handle_screenshot_comparison(payload: dict) -> None:
    # Return if the author of the pull request is not GitAuto itself
    print("\n\n\n\nStarting screenshot comparison")
    pull: dict = payload["pull_request"]
    if pull["user"]["login"] != GITHUB_APP_USER_NAME:
        return

    # Return if this feature is not enabled
    return

    # Get the basic information
    repo_obj: dict = payload["repository"]
    owner: str = repo_obj["owner"]["login"]
    repo: str = repo_obj["name"]
    installation_id: int = payload["installation"]["id"]
    token: str = get_installation_access_token(installation_id)
    pull_number: int = pull["number"]
    pull_url: str = pull["url"]
    pull_files_url = pull_url + "/files"
    head: dict[str, Any] = pull["head"]
    branch_name = head["ref"]
    file_changes = get_pull_request_file_changes(url=pull_files_url, token=token)
    print(dumps(file_changes, indent=2))

    # Create base arguments for GitHub API calls
    base_args = {
        "owner": owner,
        "repo": repo,
        "issue_number": pull_number,
        "pull_number": pull_number,
        "token": token,
    }

    server_process = None
    try:
        # Create temporary directory for cloning. For Mac, this is /private/tmp
        temp_dir = f"/tmp/{owner}/{repo}/pr-{pull_number}"
        os.makedirs(temp_dir, exist_ok=True)
        print(f"Created temporary directory: `{temp_dir}`")

        # Clone repository
        clone_repo(owner=owner, repo=repo, token=token, target_dir=temp_dir)
        print(f"Cloned repository to `{temp_dir}`")

        # Fetch the pull request branch
        fetch_branch(
            pull_number=pull_number, branch_name=branch_name, repo_dir=temp_dir
        )
        print(f"Fetched branch `{branch_name}`")

        # Check out the pull request branch
        switch_to_branch(branch_name=branch_name, repo_dir=temp_dir)
        print(f"Switched to pull request branch `{branch_name}`")

        # Get paths that need screenshot comparison
        paths = get_target_paths(file_changes, repo_dir=temp_dir)
        if not paths:
            return
        print(f"Found {len(paths)} target paths.")
        print(dumps(paths, indent=2))

        # Start a local server in the cloned repository directory
        get_current_branch(repo_dir=temp_dir)
        server_process = start_local_server(repo_dir=temp_dir)
        print(f"Started local server at server process ID: `{server_process.pid}`")

        # Wait for server to start
        sleep(5)

        # Temporary fixed URLs
        # prod_domain = "https://sample-html-css-website.vercel.app"
        prod_domain = "https://sample-simple-website.vercel.app"
        local_domain = "http://localhost:8080"
        # prod_domain = "https://gitauto.ai"
        # local_domain = "http://localhost:3000"

        # Generate URLs for both environments
        prod_urls = [f"{prod_domain}{path}" for path in paths]
        local_urls = [f"{local_domain}{path}" for path in paths]
        print(f"Prod URLs: {dumps(prod_urls, indent=2)}")
        print(f"Local URLs: {dumps(local_urls, indent=2)}")

        # Create temporary directories for screenshots
        prod_dir = os.path.join(temp_dir, "prod_screenshots")
        local_dir = os.path.join(temp_dir, "local_screenshots")
        print(f"Prod dir: {prod_dir}")
        print(f"Local dir: {local_dir}")

        # Capture screenshots
        await capture_screenshots(urls=prod_urls, output_dir=prod_dir)
        await capture_screenshots(urls=local_urls, output_dir=local_dir)

        # Delete existing screenshot comparison comments if any
        table_header = "| Before (production) | After (this branch) |\n|-------------------|----------------|\n"
        comments = get_all_comments(base_args)
        for comment in comments:
            if table_header in comment.get("body", ""):
                delete_a_comment(base_args, comment["id"])
        print("Deleted old screenshot comparison comments")

        # Upload screenshots and create comparison comments
        timestamp = str(int(time()))
        for path in paths:
            file_name = get_url_filename(path)
            prod_file = os.path.join(prod_dir, file_name)
            local_file = os.path.join(local_dir, file_name)
            print(f"Named prod file: {prod_file}")
            print(f"Named local file: {local_file}")

            if not (os.path.exists(prod_file) and os.path.exists(local_file)):
                print(f"Skipping {path} because one or both files do not exist")
                continue

            # Upload to S3 using existing directory structure
            prod_s3_key = os.path.relpath(prod_file, "/tmp")
            local_s3_key = os.path.relpath(local_file, "/tmp")

            # Upload to S3
            prod_url = upload_to_s3(file_path=prod_file, s3_key=prod_s3_key)
            print(f"Uploaded prod screenshot to S3: {prod_url}")
            local_url = upload_to_s3(file_path=local_file, s3_key=local_s3_key)
            print(f"Uploaded local screenshot to S3: {local_url}")

            # Create comparison comment
            comment_body = f"""Path: {path}\n\n{table_header}| <img src="{prod_url}?t={timestamp}" width="400" referrerpolicy="no-referrer"/> | <img src="{local_url}?t={timestamp}" width="400" referrerpolicy="no-referrer"/> |"""
            create_comment(body=comment_body, base_args=base_args)
            print(f"Created comparison comment for {path}")

    finally:
        # Cleanup: Stop the local server and remove cloned repository
        if server_process:
            server_process.terminate()
            server_process.wait()
            print(f"Terminated local server at process ID: `{server_process.pid}`")

        # Remove cloned repository
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            print(f"Deleted the temporary directory: `{temp_dir}`")
