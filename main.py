"""
bamf — Entry point.

Run with:
    python main.py

Add new menu options here by importing an operation from github_ops
and calling register_option() before run_menu_loop().
"""

import os
import sys

from auth import get_github_client
from github_ops import clone_all_repos, create_repo, list_repos, search_build_files, show_pat_info, search_actions_files, list_unprotected_repos
from menu import register_option, run_menu_loop


def main() -> None:
    client, token = get_github_client()
    os.system("cls" if os.name == "nt" else "clear")

    # Register menu options — order determines numbering.
    # To add a new feature: import it from github_ops and add a register_option() line here.
    register_option("List all repos",              lambda: list_repos(client))
    register_option("Clone all repos",             lambda: clone_all_repos(client, token))
    register_option("Create a repo",               lambda: create_repo(client))
    register_option("Search for build files",      lambda: search_build_files(client))
    register_option("Show PAT info",               lambda: show_pat_info(client, token))
    register_option("Search for Actions files",    lambda: search_actions_files(client))
    register_option("Repos without branch protection", lambda: list_unprotected_repos(client))
    register_option("Exit", None)

    run_menu_loop()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted. Exiting.")
        sys.exit(0)
