"""
bamf — Entry point.

Run with:
    python main.py

Add new menu options here by importing an operation from github_ops
and calling register_option() before run_menu_loop().
"""

import argparse
import os
import sys

from auth import get_github_client
from github_ops import (
    audit_actions_secrets,
    audit_branch_protection,
    audit_collaborators,
    audit_deploy_keys,
    audit_security_posture,
    audit_webhooks,
    clone_all_repos,
    clone_private_to_public,
    create_repo,
    edit_manifest_file,
    list_dependabot_alerts,
    list_repos,
    list_unprotected_repos,
    nuke_a_branch,
    nuke_repo,
    scan_secrets,
    search_actions_files,
    search_build_files,
    search_manifest_files,
    show_pat_info,
)
from menu import register_option, run_menu_loop


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--token", metavar="PAT", default=None,
                        help="GitHub Personal Access Token (skips interactive prompt)")
    args, _ = parser.parse_known_args()

    client, token = get_github_client(token=args.token)
    os.system("cls" if os.name == "nt" else "clear")

    # Register menu options — order determines numbering.
    # To add a new feature: import it from github_ops and add a register_option() line here.
    register_option("List all repos",              lambda: list_repos(client))
    register_option("Clone all repos",             lambda: clone_all_repos(client, token))
    register_option("Clone private to public",     lambda: clone_private_to_public(client, token))
    register_option("Create a repo",               lambda: create_repo(client))
    register_option("Search for build files",      lambda: search_build_files(client))
    register_option("Show PAT info",               lambda: show_pat_info(client, token))
    register_option("Search for Actions files",    lambda: search_actions_files(client))
    register_option("Repos without branch protection", lambda: list_unprotected_repos(client))
    register_option("Search for manifest files",       lambda: search_manifest_files(client))
    register_option("Edit a manifest file",            lambda: edit_manifest_file(client))
    register_option("Scan repos for secrets",          lambda: scan_secrets(client, token))
    register_option("Security posture audit",          lambda: audit_security_posture(client))
    register_option("Dependabot vulnerability alerts", lambda: list_dependabot_alerts(client))
    register_option("Branch protection deep-dive",     lambda: audit_branch_protection(client))
    register_option("Webhook audit",                   lambda: audit_webhooks(client))
    register_option("Collaborator access audit",       lambda: audit_collaborators(client))
    register_option("Deploy keys audit",               lambda: audit_deploy_keys(client))
    register_option("Actions secrets audit",           lambda: audit_actions_secrets(client))
    register_option("Nuke a branch (remove branch protections)", lambda: nuke_a_branch(client))
    register_option("Nuke a repo (delete permanently)", lambda: nuke_repo(client))
    register_option("Exit", None)

    run_menu_loop()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted. Exiting.")
        sys.exit(0)
