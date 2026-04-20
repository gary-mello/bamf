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
    add_collaborator,
    audit_actions_permissions,
    audit_actions_pinning,
    audit_actions_secrets,
    audit_branch_protection,
    audit_collaborators,
    audit_deploy_keys,
    audit_environment_protection,
    audit_security_posture,
    audit_webhooks,
    clone_all_repos,
    clone_private_to_public,
    create_repo,
    edit_manifest_file,
    fork_repo,
    list_dependabot_alerts,
    list_repos,
    list_unprotected_repos,
    nuke_a_branch,
    nuke_repo,
    pwn_inject_workflow,
    scan_pull_request_target,
    scan_secrets,
    scan_self_hosted_runners,
    scan_workflow_injection,
    search_actions_files,
    search_build_files,
    search_manifest_files,
    show_pat_info,
)
from menu import register_option, register_section, run_menu_loop


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--token", metavar="PAT", default=None,
                        help="GitHub Personal Access Token (skips interactive prompt)")
    args, _ = parser.parse_known_args()

    client, token, scopes = get_github_client(token=args.token)

    def no_perm(*required_any: str) -> bool:
        """Return True (disabled) when scopes are known and none of the required ones are present."""
        if not scopes:
            return False
        return not any(s in scopes for s in required_any)

    # Register menu options — order determines numbering.
    # To add a new feature: import it from github_ops and add a register_option() line here.
    register_section("RECON")
    register_option("List all repos",                  lambda: list_repos(client))
    register_option("Show PAT info",                   lambda: show_pat_info(client, token))
    register_option("Search for build files",          lambda: search_build_files(client),          disabled=no_perm("repo"))
    register_option("Search for Actions files",        lambda: search_actions_files(client),        disabled=no_perm("repo"))
    register_option("Search for manifest files",       lambda: search_manifest_files(client),       disabled=no_perm("repo"))
    register_option("Repos without branch protection", lambda: list_unprotected_repos(client),      disabled=no_perm("repo"))
    register_option("Security posture audit",          lambda: audit_security_posture(client),      disabled=no_perm("repo"))
    register_option("Dependabot vulnerability alerts", lambda: list_dependabot_alerts(client),      disabled=no_perm("repo"))
    register_option("Branch protection deep-dive",     lambda: audit_branch_protection(client),     disabled=no_perm("repo"))
    register_option("Webhook audit",                   lambda: audit_webhooks(client),              disabled=no_perm("repo"))
    register_option("Collaborator access audit",       lambda: audit_collaborators(client),         disabled=no_perm("repo"))
    register_option("Deploy keys audit",               lambda: audit_deploy_keys(client),           disabled=no_perm("repo"))
    register_option("Actions secrets audit",           lambda: audit_actions_secrets(client),       disabled=no_perm("repo"))
    register_option("Scan repos for secrets",          lambda: scan_secrets(client, token),         disabled=no_perm("repo"))
    register_option("Workflow injection scan",         lambda: scan_workflow_injection(client),      disabled=no_perm("repo"))
    register_option("Actions permissions audit",       lambda: audit_actions_permissions(client),    disabled=no_perm("repo"))
    register_option("pull_request_target scan",        lambda: scan_pull_request_target(client),     disabled=no_perm("repo"))
    register_option("Self-hosted runner detection",    lambda: scan_self_hosted_runners(client),     disabled=no_perm("repo"))
    register_option("Actions pinning audit",           lambda: audit_actions_pinning(client),        disabled=no_perm("repo"))
    register_option("Environment protection audit",    lambda: audit_environment_protection(client), disabled=no_perm("repo"))

    register_section("PWN")
    register_option("Clone all repos",                  lambda: clone_all_repos(client, token),          disabled=no_perm("repo"))
    register_option("Clone private to public",          lambda: clone_private_to_public(client, token),  disabled=no_perm("repo"))
    register_option("Create a repo",                    lambda: create_repo(client),                     disabled=no_perm("repo", "public_repo"))
    register_option("Edit a manifest file",             lambda: edit_manifest_file(client),              disabled=no_perm("repo"))
    register_option("Nuke branch protections",          lambda: nuke_a_branch(client),                   disabled=no_perm("repo"))
    register_option("Nuke a repo (delete permanently)", lambda: nuke_repo(client),                       disabled=no_perm("delete_repo"))
    register_option("Add collaborator",                 lambda: add_collaborator(client),                disabled=no_perm("repo"))
    register_option("Inject test workflow (PWN)",       lambda: pwn_inject_workflow(client),             disabled=no_perm("repo"))
    register_option("Fork a repo",                      lambda: fork_repo(client),                       disabled=no_perm("repo", "public_repo"))

    run_menu_loop()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted. Exiting.")
        sys.exit(0)
