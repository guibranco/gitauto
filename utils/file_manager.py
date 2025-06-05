import logging
import os
import re
import subprocess
import tempfile

from config import UTF8
from security import safe_command


def apply_patch(original_text: str, diff_text: str) -> str:
    """Apply a diff using the patch command via temporary files"""
    with tempfile.NamedTemporaryFile(
        mode="w+", newline="", delete=False
    ) as original_file:
        org_fname: str = original_file.name
        if original_text:
            original_file.write(
                original_text if original_text.endswith("\n") else original_text + "\n"
            )

    with tempfile.NamedTemporaryFile(mode="w+", newline="", delete=False) as diff_file:
        diff_fname: str = diff_file.name
        diff_file.write(diff_text if diff_text.endswith("\n") else diff_text + "\n")

    modified_text = ""
    try:
        # New file
        if original_text == "" and "+++ " in diff_text:
            lines: list[str] = diff_text.split(sep="\n")
            new_content_lines: list[str] = [
                line[1:] if line.startswith("+") else line for line in lines[3:]
            ]
            new_content: str = "\n".join(new_content_lines)
            with open(file=org_fname, mode="w", encoding=UTF8, newline="") as new_file:
                new_file.write(new_content)

        # Modified or deleted file
        else:
            with open(file=diff_fname, mode="r", encoding=UTF8, newline="") as diff:
                safe_command.run(subprocess.run, args=["patch", "-u", "--fuzz=3", org_fname],
                    input=diff.read(),
                    text=True,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

        print("Patch applied successfully.")
        with open(file=org_fname, mode="r", encoding=UTF8, newline="") as modified_file:
            modified_text: str = modified_file.read()
            print(f"{modified_text=}\n")

    except subprocess.CalledProcessError as e:
        stdout, stderr = e.stdout, e.stderr
        cmd, code = " ".join(e.cmd), e.returncode

        # Get the original, diff, and reject file contents for debugging
        with open(file=org_fname, mode="r", encoding=UTF8, newline="") as modified_file:
            modified_text: str = modified_file.read()
        with open(file=diff_fname, mode="r", encoding=UTF8, newline="") as diff_file:
            diff_text: str = diff_file.read()
        rej_f_name: str = f"{org_fname}.rej"
        reject_text = None
        if os.path.exists(path=rej_f_name):
            with open(file=rej_f_name, mode="r", encoding=UTF8, newline="") as rej_file:
                reject_text = rej_file.read()

        # Log the error and return an empty string not to break the flow
        msg = f"Failed to apply patch. stdout: {stdout}\n\nDiff content: {diff_text}\n\nReject content: {reject_text}\n\nOriginal content: {original_text}"
        logging.error(msg=msg)
        logging.info("stderr: %s\nCommand: %s\nReturn code: %s", stderr, cmd, code)
        return modified_text

    except Exception as e:  # pylint: disable=broad-except
        logging.error(msg=f"Error: {e}")
        return ""
    finally:
        os.remove(path=org_fname)
        os.remove(path=diff_fname)
        print("Temporary files removed.\n")

    return modified_text


def clean_specific_lines(text: str) -> str:
    return "\n".join(
        [
            line
            for line in text.strip().split(sep="\n")
            if line.startswith(("+++", "---", "@@", "+", "-"))
        ]
    ).strip()


def correct_hunk_headers(diff_text: str) -> str:
    """
    Match following patterns:
    1: @@ -start1 +start2 @@
    2: @@ -start1,lines1 +start2 @@
    3: @@ -start1 +start2,lines2 @@
    4: @@ -start1,lines1 +start2,lines2 @@
    """
    # Split the diff into lines
    lines: list[str] = diff_text.splitlines()
    updated_lines: list[str] = []
    hunk_pattern: re.Pattern[str] = re.compile(
        pattern=r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@"
    )

    i = 0
    while i < len(lines):
        line: str = lines[i]
        match: re.Match[str] | None = hunk_pattern.match(string=line)

        # Add the line to the updated diff if it's not a hunk header
        if not match:
            updated_lines.append(line)
            i += 1
            continue

        # Correct the hunk header if match is not None
        l1, _s1, l2, _s2 = (int(x) if x is not None else 0 for x in match.groups())
        s1_actual, s2_actual = 0, 0
        i += 1

        # Count actual number of lines changed
        start_index: int = i
        while i < len(lines) and not lines[i].startswith("@@"):
            if lines[i].startswith("+"):
                s2_actual += 1
            if lines[i].startswith("-"):
                s1_actual += 1
            i += 1

        # Update the hunk header with actual numbers
        updated_hunk_header: str = f"@@ -{l1},{s1_actual} +{l2},{s2_actual} @@"
        updated_lines.append(updated_hunk_header)
        updated_lines.extend(lines[start_index:i])

    return "\n".join(updated_lines)


def extract_file_name(diff_text: str) -> str:
    match = re.search(pattern=r"^\+\+\+ (.+)$", string=diff_text, flags=re.MULTILINE)
    if match:
        return match.group(1)
    raise ValueError("No file name found in the diff text.")


def run_command(command: str, cwd: str) -> str:
    try:
        result: subprocess.CompletedProcess[str] = safe_command.run(subprocess.run, args=command,
            capture_output=True,
            check=True,
            cwd=cwd,
            text=True,
            shell=True,
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        raise ValueError(f"Command failed: {e.stderr}") from e


def split_diffs(diff_text: str) -> list[str]:
    file_diffs: list[str] = re.split(
        pattern=r"(?=^---\s)", string=diff_text, flags=re.MULTILINE
    )

    # Remove the first element if it's an empty string
    if file_diffs and file_diffs[0] == "":
        file_diffs.pop(0)

    # Remove leading and trailing whitespace from each diff
    cleaned_diffs: list[str] = []
    for diff in file_diffs:
        stripped_diff: str = diff.strip()
        if not stripped_diff.endswith("\n"):
            stripped_diff += "\n"
        cleaned_diffs.append(stripped_diff)

    return cleaned_diffs
