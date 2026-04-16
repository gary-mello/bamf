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

from colors import bold, cyan, green, red, yellow, reset, dim


MAX_RETRIES = 3


def get_github_client(token: str | None = None) -> tuple[Github, str]:
    """Prompt for a GitHub PAT (or use a provided one), verify it, and return (Github client, raw token).

    If *token* is supplied (e.g. from --token CLI flag) the interactive prompt is skipped
    and the token is validated immediately with no retries.

    The raw token is returned so callers can use it for authenticated git operations
    (e.g. embedding it in an HTTPS clone URL).

    Retries up to MAX_RETRIES times on bad credentials (interactive mode only).
    Exits with code 1 after exhausting retries or on unrecoverable errors.
    """
    if sys.platform == "win32":
        import os; os.system("cls")
    else:
        sys.stdout.write("\033[2J\033[3J\033[H")
        sys.stdout.flush()

    bar = f"{bold}{cyan}{'═' * 42}{reset}"

    # ── Non-interactive: token supplied via flag ─────────────────────────────
    if token:
        print(bar)
        print(f"{bold}{cyan}{'  bamf — Authentication':^42}{reset}")
        print(bar)
        try:
            client = Github(token)
            login = client.get_user().login
            print(f"\n  {green}{bold}Authenticated as: {login}{reset}\n")
            return client, token
        except GithubException as exc:
            if exc.status == 401:
                print(f"  {red}Bad credentials in --token flag. Exiting.{reset}")
            else:
                print(f"  {red}GitHub error ({exc.status}): {exc.data.get('message', str(exc))}{reset}")
            sys.exit(1)
        except requests.exceptions.ConnectionError:
            print(f"  {red}Cannot reach GitHub. Check your network connection and try again.{reset}")
            sys.exit(1)

    # ── Interactive: prompt for token ────────────────────────────────────────
    print(bar)
    print(f"{bold}{cyan}{'  bamf — Authentication':^42}{reset}")
    print(bar)
    print(f"  Enter your Personal Access Token {dim}(input is hidden){reset}")
    print(f"  {dim}Generate one at: https://github.com/settings/tokens{reset}\n")

    for attempt in range(1, MAX_RETRIES + 1):
        token = getpass.getpass(f"  {bold}GitHub Token:{reset} ").strip()

        if not token:
            print(f"  {red}Token cannot be empty. Please try again.{reset}\n")
            continue

        try:
            client = Github(token)
            login = client.get_user().login  # verifies credentials immediately
            print(f"\n  {green}{bold}Authenticated as: {login}{reset}\n")
            return client, token

        except GithubException as exc:
            if exc.status == 401:
                remaining = MAX_RETRIES - attempt
                if remaining > 0:
                    print(f"  {red}Bad credentials.{reset} {yellow}{remaining} attempt(s) remaining.{reset}\n")
                else:
                    print(f"  {red}Bad credentials. No attempts remaining.{reset}")
            else:
                print(f"  {red}GitHub error ({exc.status}): {exc.data.get('message', str(exc))}{reset}")
                sys.exit(1)

        except requests.exceptions.ConnectionError:
            print(f"  {red}Cannot reach GitHub. Check your network connection and try again.{reset}")
            sys.exit(1)

    print(f"{red}Authentication failed. Exiting.{reset}")
    sys.exit(1)
