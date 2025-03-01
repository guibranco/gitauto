import subprocess
from utils.handle_exceptions import handle_exceptions
from security import safe_command


@handle_exceptions(raise_on_error=True)
def clone_repo(owner: str, repo: str, token: str, target_dir: str):
    repo_url = f"https://x-access-token:{token}@github.com/{owner}/{repo}.git"
    clone_cmd = f"git clone {repo_url} {target_dir}"
    safe_command.run(subprocess.run, clone_cmd, shell=True, capture_output=True, text=True, check=True)


@handle_exceptions(raise_on_error=True)
def fetch_branch(pull_number: int, branch_name: str, repo_dir: str):
    cmd = f"git fetch origin pull/{pull_number}/head:{branch_name}"
    safe_command.run(subprocess.run, cmd, shell=True, capture_output=True, text=True, check=True, cwd=repo_dir
    )


@handle_exceptions(default_return_value=None, raise_on_error=False)
def get_current_branch(repo_dir: str):
    cmd = "git branch --show-current"
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, check=True, cwd=repo_dir
    )
    print(f"Current branch: `{result.stdout.strip()}`")


@handle_exceptions(raise_on_error=True)
def start_local_server(repo_dir: str):
    command = "python -m http.server 8080"
    # command = "npm run dev"
    server_process = safe_command.run(subprocess.Popen, args=command,
        shell=True,
        cwd=repo_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return server_process


@handle_exceptions(raise_on_error=True)
def switch_to_branch(branch_name: str, repo_dir: str):
    """Supports deleted branches and branches in forked repositories. https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests/checking-out-pull-requests-locally"""
    switch_cmd = f"git switch {branch_name}"
    safe_command.run(subprocess.run, switch_cmd, shell=True, capture_output=True, text=True, check=True, cwd=repo_dir
    )
