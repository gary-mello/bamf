"""
GitHub authentication module.

Prompts for a Personal Access Token (PAT) and validates it against the GitHub API.

Token requirements:
  - Classic PAT: needs 'repo' scope for private repos and cloning; any valid token works for public repos.
  - Fine-Grained PAT: grant read/write access to the repos you want to manage.
  Generate one at: https://github.com/settings/tokens
"""

import getpass
import sys

from github import Github, GithubException
import requests


MAX_RETRIES = 3


def get_github_client() -> tuple[Github, str]:
    """Prompt for a GitHub PAT, verify it, and return (Github client, raw token).

    The raw token is returned so callers can use it for authenticated git operations
    (e.g. embedding it in an HTTPS clone URL).

    Retries up to MAX_RETRIES times on bad credentials.
    Exits with code 1 after exhausting retries or on unrecoverable errors.
    """
    print("GitHub CLI — Authentication")
    print("Enter your Personal Access Token (PAT). Input is hidden.")
    print("Generate one at: https://github.com/settings/tokens\n")

    for attempt in range(1, MAX_RETRIES + 1):
        token = getpass.getpass("GitHub Token: ").strip()

        if not token:
            print("  Token cannot be empty. Please try again.\n")
            continue

        try:
            client = Github(token)
            login = client.get_user().login  # verifies credentials immediately
            print(f"\n  Authenticated as: {login}\n")
            return client, token

        except GithubException as exc:
            if exc.status == 401:
                remaining = MAX_RETRIES - attempt
                if remaining > 0:
                    print(f"  Bad credentials. {remaining} attempt(s) remaining.\n")
                else:
                    print("  Bad credentials. No attempts remaining.")
            else:
                print(f"  GitHub error ({exc.status}): {exc.data.get('message', str(exc))}")
                sys.exit(1)

        except requests.exceptions.ConnectionError:
            print("  Cannot reach GitHub. Check your network connection and try again.")
            sys.exit(1)

    print("Authentication failed. Exiting.")
    sys.exit(1)
