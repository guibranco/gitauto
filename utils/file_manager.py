# Standard imports
import os
import subprocess
import tempfile

# Third-party imports
import chardet

# Local imports
from config import UTF8
from utils.detect_new_line import detect_line_break
from utils.handle_exceptions import handle_exceptions
from security import safe_command


def apply_patch(original_text: str, diff_text: str):
    """Apply a diff using the patch command via temporary files.
    Here is comparison of patch options in handling "Assume -R?" and "Apply anyway?" prompts:

    --forward:
    Assume -R? [n]: No
    Apply anyway? [n]: No

    --batch:
    Assume -R? [y]: Yes
    Apply anyway? [y]: Yes

    --force:
    Assume -R? [n]: No
    Apply anyway? [y]: Yes
    """

    # Detect the line break in the original text
    line_break: str = detect_line_break(text=original_text)

    # Create temporary files as subprocess.run() accepts only file paths
    with tempfile.NamedTemporaryFile(
        mode="w+", encoding=UTF8, newline="\n", delete=False
    ) as org_file:
        org_fname: str = org_file.name
        if original_text:
            s = original_text.replace("\r\n", "\n").replace("\r", "\n")
            if not s.endswith("\n"):
                s += "\n"
            org_file.write(s)

    with tempfile.NamedTemporaryFile(
        mode="w+", encoding=UTF8, newline="\n", delete=False
    ) as diff_file:
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
            with open(
                file=org_fname, mode="w", encoding=UTF8, newline="\n"
            ) as new_file:
                new_file.write(new_content)

        # Modified or deleted file
        else:
            with open(file=diff_fname, mode="r", encoding=UTF8, newline="\n") as diff:
                safe_command.run(subprocess.run, args=["patch", "-u", "--fuzz=3", "--forward", org_fname],
                    input=diff.read(),
                    text=True,  # If True, input and output are strings
                    encoding=UTF8,
                    # capture_output=True,  # Redundant so commented out
                    check=True,  # If True, raise a CalledProcessError if the return code is non-zero
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

        # If the patch was successfully applied, get the modified text
        modified_text = get_file_content(file_path=org_fname)
        modified_text = modified_text.replace("\n", line_break)

    except subprocess.CalledProcessError as e:
        stdout: str = e.stdout
        stderr: str = e.stderr

        # Check if the error message indicates that the patch was already applied
        msg = f"Failed to apply patch because the diff is already applied. But it's OK, move on to the next fix!\n\ndiff_text:\n{diff_text}\n\nstderr:\n{stderr}\n"
        if "already exists!" in stdout:
            # print(msg, end="")
            return "", msg
        if "Ignoring previously applied (or reversed) patch." in stdout:
            # print(msg, end="")
            return "", msg

        # Get the original, diff, and reject file contents for debugging
        modified_text = get_file_content(file_path=org_fname)
        modified_text = modified_text.replace("\n", line_break)
        diff_text = (
            get_file_content(file_path=diff_fname).replace(" ", "·").replace("\t", "→").replace("\\t", "→")
        )
        rej_f_name: str = f"{org_fname}.rej"
        rej_text = ""
        if os.path.exists(path=rej_f_name):
            rej_text = (
                get_file_content(file_path=rej_f_name)
                .replace(" ", "·")
                .replace("\t", "→")
            )

        # Log the error and return an empty string not to break the flow
        msg = f"Failed to apply patch partially or entirelly because something is wrong in diff. Analyze the reason from stderr and rej_text, modify the diff, and try again.\n\ndiff_text:\n{diff_text}\n\nstderr:\n{stderr}\n\nrej_text:\n{rej_text}\n"
        # Print encodings of input texts
        print(f"Org encoding: {chardet.detect(original_text.encode())['encoding']}")
        print(f"Diff encoding: {chardet.detect(diff_text.encode())['encoding']}")
        print(msg, end="")
        # logging.error(msg)
        return modified_text, msg

    except Exception as e:  # pylint: disable=broad-except
        print(f"Error: {e}", end="")
        # logging.error(msg=f"Error: {e}")
        return "", f"Error: {e}"
    finally:
        # Remove temporary files
        os.remove(path=org_fname)
        os.remove(path=diff_fname)

        # Remove any Oops.rej* files in the root directory
        root_dir = os.getcwd()
        for filename in os.listdir(root_dir):
            if filename.startswith("Oops.rej"):
                os.remove(os.path.join(root_dir, filename))

    return modified_text, ""


@handle_exceptions(default_return_value="", raise_on_error=False)
def get_file_content(file_path: str) -> str:
    with open(file=file_path, mode="r", encoding=UTF8, newline="\n") as file:
        return file.read()


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
        # 127: Command not found so check if Git is installed
        if e.returncode == 127:
            try:
                # Check if Git is installed
                version_result = safe_command.run(subprocess.run, args="git --version",
                    capture_output=True,
                    check=True,
                    text=True,
                    shell=True,
                )
                print(f"Git version: {version_result.stdout}", end="")
                # logging.info("Git version: %s", version_result.stdout)
            except subprocess.CalledProcessError as ve:
                print(f"Failed to get Git version: {ve.stderr}", end="")
                # logging.error("Failed to get Git version: %s", ve.stderr)

        raise ValueError(f"Command failed: {e.stderr}") from e
