from datetime import datetime

# Local imports
from config import EMAIL_LINK, PRODUCT_ID
from constants.messages import COMPLETED_PR


def git_command(new_branch_name: str) -> str:
    return (
        "\n\n## Test these changes locally\n\n"
        "```\n"
        "git fetch origin\n"
        f"git checkout {new_branch_name}\n"
        f"git pull origin {new_branch_name}\n"
        "```"
    )


def request_limit_reached(
    user_name: str, request_count: int, end_date: datetime
) -> str:
    return f"Hello @{user_name}, you have reached your request limit of {request_count}, your cycle will refresh on {end_date}.\nConsider <a href='https://gitauto.ai/#pricing'>subscribing</a> if you want more requests.\nIf you have any questions or concerns, please contact us at {EMAIL_LINK}."


def pull_request_completed(
    issuer_name: str, sender_name: str, pr_url: str, is_automation: bool
) -> str:
    # Ex) sentry-io[bot] is the issuer and gitauto-ai[bot] is the sender
    if "[bot]" in issuer_name and ("[bot]" in sender_name or PRODUCT_ID in sender_name):
        user_part = ""

    elif "[bot]" in issuer_name and (
        "[bot]" not in sender_name and PRODUCT_ID not in sender_name
    ):
        user_part = f"@{sender_name} "

    # Ex1) A user is the issuer and sender
    # Ex2) sender_name contains gitauto
    elif issuer_name == sender_name or PRODUCT_ID in sender_name:
        user_part = f"@{issuer_name} "

    # Ex) A user is the issuer and another user is the sender
    else:
        user_part = f"@{issuer_name} @{sender_name} "

    # For user triggers
    if not is_automation:
        return f"{user_part}{COMPLETED_PR} {pr_url} 🚀\nShould you have any questions or wish to change settings or limits, please feel free to contact {EMAIL_LINK} or invite us to Slack Connect."

    # For automation triggers
    return f"{user_part}{COMPLETED_PR} {pr_url} 🚀\n\nNote: I automatically create a pull request for an unassigned and open issue in order from oldest to newest once a day at 00:00 UTC, as long as you have remaining automation usage. Should you have any questions or wish to change settings or limits, please feel free to contact {EMAIL_LINK} or invite us to Slack Connect."


def request_issue_comment(requests_left: int, sender_name: str, end_date: datetime):
    requests_left = 0 if requests_left < 0 else requests_left
    plural = "" if requests_left == 1 else "s"
    return f"\n\n@{sender_name}, You have {requests_left} request{plural} left in this cycle which refreshes on {end_date}.\nIf you have any questions or concerns, please contact us at {EMAIL_LINK}."


UPDATE_COMMENT_FOR_422 = f"Hey, I'm a bit lost here! Not sure which file I should be fixing. Could you give me a bit more to go on? Maybe add some details to the issue or drop a comment with some extra hints? Thanks!\n\nHave feedback or need help?\nFeel free to email {EMAIL_LINK}."
UPDATE_COMMENT_FOR_RAISED_ERRORS_NO_CHANGES_MADE = f"No changes were detected. Please add more details to the issue and try again.\n\nHave feedback or need help?\n{EMAIL_LINK}"
