# Standard imports
import base64
import datetime
import os

# Third-party imports
from dotenv import load_dotenv

load_dotenv()


def get_env_var(name: str) -> str:
    value: str | None = os.environ.get(name)
    if value is None:
        raise ValueError(f"Environment variable {name} not set.")
    return value


# GitHub Credentials from environment variables
GITHUB_API_URL: str = "https://api.github.com"
GITHUB_API_VERSION: str = "2022-11-28"
GITHUB_APP_ID = int(get_env_var(name="GH_APP_ID"))
GITHUB_APP_IDS: list[int] = list({GITHUB_APP_ID,  # Production or your local development
    844909,  # Production
    901480})
GITHUB_APP_USER_ID: int = int(get_env_var(name="GH_APP_USER_ID"))
GITHUB_APP_USER_NAME: str = get_env_var(name="GH_APP_USER_NAME")
GITHUB_PRIVATE_KEY_ENCODED: str = get_env_var(name="GH_PRIVATE_KEY")
GITHUB_PRIVATE_KEY: bytes = base64.b64decode(s=GITHUB_PRIVATE_KEY_ENCODED)
GITHUB_WEBHOOK_SECRET: str = get_env_var(name="GH_WEBHOOK_SECRET")

# OpenAI Credentials from environment variables
OPENAI_API_KEY: str = get_env_var(name="OPENAI_API_KEY")
OPENAI_FINAL_STATUSES: list[str] = ["cancelled", "completed", "expired", "failed"]
OPENAI_MAX_TOKENS = 4096
OPENAI_MODEL_ID = "gpt-4o"
OPENAI_ORG_ID: str = get_env_var(name="OPENAI_ORG_ID")
OPENAI_TEMPERATURE = 0.0

# Supabase Credentials from environment variables
SUPABASE_SERVICE_ROLE_KEY: str = get_env_var(name="SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_URL: str = get_env_var(name="SUPABASE_URL")

# Stripe
STRIPE_API_KEY: str = get_env_var(name="STRIPE_API_KEY")
STRIPE_FREE_TIER_PRICE_ID: str = get_env_var(name="STRIPE_FREE_TIER_PRICE_ID")

# General
DEFAULT_TIME = datetime.datetime(year=1, month=1, day=1, hour=0, minute=0, second=0)
EMAIL_LINK = "[info@gitauto.ai](mailto:info@gitauto.ai)"
ENV: str = get_env_var(name="ENV")
# Update here too: https://dashboard.stripe.com/test/products/prod_PokLGIxiVUwCi6
FREE_TIER_REQUEST_AMOUNT = 5
ISSUE_NUMBER_FORMAT = "/issue-#"
PR_BODY_STARTS_WITH = "Original issue: [#"
PRODUCT_ID: str = get_env_var(name="PRODUCT_ID")
PRODUCT_NAME = "GitAuto"
PRODUCT_URL = "https://gitauto.ai"
TIMEOUT_IN_SECONDS = 120
UTF8 = "utf-8"

# Testing
INSTALLATION_ID = -1
NEW_INSTALLATION_ID = -2
OWNER_ID = -1
OWNER_NAME = "installation-test"
OWNER_TYPE = "Organization"
UNIQUE_ISSUE_ID = "O/gitautoai/test#1"
USER_ID = -1
USER_NAME = "username-test"
