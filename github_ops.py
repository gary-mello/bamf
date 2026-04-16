"""
GitHub API operations.

Each function accepts an authenticated Github client as its first argument
and prints results directly to the terminal.
"""

import os
import shutil
import subprocess
from datetime import timezone

from github import Github, GithubException
import requests

from colors import bold, cyan, green, red, yellow, magenta, white, dim, reset, muted, header as hdr, label as lbl, success, warn, error as err, value as val


def list_repos(client: Github) -> None:
    """List all repos accessible to the authenticated user, sorted by most recently updated."""
    print(f"\n{cyan}Fetching repositories...{reset}\n")

    try:
        user = client.get_user()
        repos = user.get_repos(sort="updated", direction="desc")

        # Column widths
        COL_NUM   = 4
        COL_NAME  = 30
        COL_VIS   = 10
        COL_LANG  = 16
        COL_DESC  = 50

        col_header = (
            f"{'#':<{COL_NUM}} "
            f"{'Name':<{COL_NAME}} "
            f"{'Visibility':<{COL_VIS}} "
            f"{'Language':<{COL_LANG}} "
            f"{'Description':<{COL_DESC}}"
        )
        divider = "─" * len(col_header)

        print(f"{bold}{cyan}{col_header}{reset}")
        print(f"{dim}{divider}{reset}")

        count = 0
        for repo in repos:
            count += 1
            name = _truncate(repo.name, COL_NAME)
            visibility = "private" if repo.private else "public"
            vis_colored = f"{yellow}{'private':<{COL_VIS}}{reset}" if repo.private else f"{green}{'public':<{COL_VIS}}{reset}"
            language = repo.language or "-"
            description = _truncate(repo.description or "", COL_DESC)

            print(
                f"{dim}{count:<{COL_NUM}}{reset} "
                f"{bold}{white}{name:<{COL_NAME}}{reset} "
                f"{vis_colored} "
                f"{cyan}{language:<{COL_LANG}}{reset} "
                f"{dim}{description:<{COL_DESC}}{reset}"
            )

        print(f"{dim}{divider}{reset}")
        print(f"\n  {bold}Total:{reset} {green}{count}{reset} repo(s)\n")

    except GithubException as exc:
        if exc.status in (403, 429):
            _handle_rate_limit(client, exc)
        else:
            msg = exc.data.get("message", str(exc))
            print(f"\n  {err(f'GitHub error ({exc.status}): {msg}')}\n")

    except requests.exceptions.ConnectionError:
        print(f"\n  {err('Network error: unable to reach GitHub. Check your connection.')}\n")


def clone_all_repos(client: Github, token: str) -> None:
    """Clone all repos accessible to the authenticated user into a local directory."""
    default_dir = os.path.join(os.getcwd(), "cloned_repos")
    raw = input(f"\n{bold}Destination directory{reset} [{dim}{default_dir}{reset}]: ").strip()
    dest = raw if raw else default_dir

    if not shutil.which("git"):
        print(f"\n  {err('Error: git was not found on your PATH. Please install git and try again.')}\n")
        return

    try:
        repos = list(client.get_user().get_repos(sort="updated", direction="desc"))
    except GithubException as exc:
        msg = exc.data.get("message", str(exc))
        print(f"\n  {err(f'GitHub error ({exc.status}): {msg}')}\n")
        return
    except requests.exceptions.ConnectionError:
        print(f"\n  {err('Network error: unable to reach GitHub. Check your connection.')}\n")
        return

    if not repos:
        print(f"\n  {warn('No repositories found.')}\n")
        return

    os.makedirs(dest, exist_ok=True)
    total = len(repos)
    cloned = skipped = failed = 0

    print(f"\n{cyan}Cloning {bold}{total}{reset}{cyan} repo(s) into:{reset} {white}{dest}{reset}\n")

    for i, repo in enumerate(repos, start=1):
        repo_dir = os.path.join(dest, repo.name)
        prefix = f"  {dim}({i}/{total}){reset} {bold}{white}{repo.name}{reset}"

        if os.path.isdir(repo_dir):
            print(f"{prefix} {dim}— skipped (directory already exists){reset}")
            skipped += 1
            continue

        owner = repo.owner.login
        clone_url = f"https://x-access-token:{token}@github.com/{owner}/{repo.name}.git"

        result = subprocess.run(
            ["git", "clone", "--quiet", clone_url, repo_dir],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            vis_tag = f"{yellow}private{reset}" if repo.private else f"{green}public{reset}"
            print(f"{prefix} {green}— cloned{reset}  [{vis_tag}]")
            cloned += 1
        else:
            clone_err = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "unknown error"
            print(f"{prefix} {red}— FAILED:{reset} {clone_err}")
            failed += 1

    print(
        f"\n  {bold}Done.{reset}  "
        f"{green}Cloned: {cloned}{reset}  |  "
        f"{dim}Skipped: {skipped}{reset}  |  "
        f"{red}Failed: {failed}{reset}\n"
    )


def create_repo(client: Github) -> None:
    """Interactively create a new GitHub repository."""
    print()

    # --- Name ---
    while True:
        name = input(f"  {bold}Repository name:{reset} ").strip()
        if not name:
            print(f"  {err('Name cannot be empty. Please try again.')}")
            continue
        if " " in name:
            print(f"  {err('Name cannot contain spaces (use hyphens or underscores). Please try again.')}")
            continue
        break

    # --- Visibility ---
    while True:
        vis = input(f"  {bold}Visibility{reset} — {green}(p)ublic{reset} or {yellow}(r)ivate{reset}? [{yellow}private{reset}]: ").strip().lower()
        if vis in ("", "r", "private"):
            private = True
            break
        if vis in ("p", "public"):
            private = False
            break
        msg_vis = "Please enter 'p' for public or 'r' for private."
        print(f"  {err(msg_vis)}")

    # --- Description (optional) ---
    description = input(f"  {bold}Description{reset} {dim}(optional, press Enter to skip){reset}: ").strip()

    vis_label = f"{yellow}private{reset}" if private else f"{green}public{reset}"
    print(f"\n  Creating {vis_label} repo {cyan}'{name}'{reset}...")

    try:
        user = client.get_user()
        repo = user.create_repo(
            name,
            private=private,
            description=description or "",
            auto_init=False,
        )
        print(f"\n  {success('Repository created successfully!')}")
        print(f"  {lbl('Name:      ')} {bold}{repo.full_name}{reset}")
        print(f"  {lbl('Visibility:')} {vis_label}")
        print(f"  {lbl('Clone URL: ')} {dim}{repo.clone_url}{reset}")
        print(f"  {lbl('SSH URL:   ')} {dim}{repo.ssh_url}{reset}\n")

    except GithubException as exc:
        if exc.status == 422:
            errors = exc.data.get("errors", [])
            msg = errors[0].get("message", "invalid name or repo already exists") if errors else "invalid name or repo already exists"
            print(f"\n  {err(f'Could not create repo: {msg}')}\n")
        else:
            msg = exc.data.get("message", str(exc))
            print(f"\n  {err(f'GitHub error ({exc.status}): {msg}')}\n")

    except requests.exceptions.ConnectionError:
        print(f"\n  {err('Network error: unable to reach GitHub. Check your connection.')}\n")


def search_build_files(client: Github) -> None:
    """Scan all accessible repos for build/CI files and report findings."""

    # Map of filename → build system label (checked against root directory listing)
    BUILD_FILES: dict[str, str] = {
        "Makefile":           "Make",
        "makefile":           "Make",
        "GNUmakefile":        "Make (GNU)",
        "CMakeLists.txt":     "CMake",
        "pom.xml":            "Maven",
        "build.gradle":       "Gradle",
        "build.gradle.kts":   "Gradle (Kotlin DSL)",
        "settings.gradle":    "Gradle (multi-project)",
        "build.xml":          "Ant",
        "package.json":       "npm / Node",
        "Cargo.toml":         "Cargo (Rust)",
        "go.mod":             "Go Modules",
        "setup.py":           "Python setuptools",
        "pyproject.toml":     "Python PEP 517",
        "setup.cfg":          "Python setuptools (cfg)",
        "tox.ini":            "tox (Python testing)",
        "Dockerfile":         "Docker",
        "docker-compose.yml": "Docker Compose",
        "docker-compose.yaml":"Docker Compose",
        "Rakefile":           "Rake (Ruby)",
        "Gemfile":            "Bundler (Ruby)",
        "meson.build":        "Meson",
        "Justfile":           "Just",
        "justfile":           "Just",
        "Taskfile.yml":       "Task",
        "Taskfile.yaml":      "Task",
    }

    try:
        repos = list(client.get_user().get_repos(sort="updated", direction="desc"))
    except GithubException as exc:
        msg = exc.data.get("message", str(exc))
        print(f"\n  {err(f'GitHub error ({exc.status}): {msg}')}\n")
        return
    except requests.exceptions.ConnectionError:
        print(f"\n  {err('Network error: unable to reach GitHub. Check your connection.')}\n")
        return

    if not repos:
        print(f"\n  {warn('No repositories found.')}\n")
        return

    total = len(repos)
    print(f"\n{cyan}Scanning {bold}{total}{reset}{cyan} repo(s) for build files...{reset}\n")

    hits = 0

    for i, repo in enumerate(repos, start=1):
        print(f"  {dim}Checking ({i}/{total}): {repo.name} ...{reset}", end="\r", flush=True)

        # --- Derive PAT access level for this repo ---
        perms = repo.permissions
        if perms is None:
            access = "unknown"
        elif perms.admin:
            access = "admin"
        elif perms.push:
            access = "write"
        elif perms.pull:
            access = "read"
        else:
            access = "none"

        # --- Fetch root directory contents (single API call) ---
        try:
            root_contents = repo.get_contents("")
        except GithubException:
            continue

        root_names = {item.name: item for item in root_contents}

        # --- Match against known build file names ---
        found: list[str] = []
        for filename, build_label in BUILD_FILES.items():
            if filename in root_names:
                found.append(f"    {cyan}{filename:<30}{reset}  {dim}{build_label}{reset}")

        # --- Check .github/workflows for GitHub Actions ---
        actions_count = 0
        if ".github" in root_names:
            try:
                workflows = repo.get_contents(".github/workflows")
                yml_files = [
                    f for f in (workflows if isinstance(workflows, list) else [workflows])
                    if f.name.endswith((".yml", ".yaml"))
                ]
                actions_count = len(yml_files)
                if actions_count:
                    wf_label = f"GitHub Actions  ({actions_count} workflow{'s' if actions_count != 1 else ''})"
                    found.append(f"    {magenta}{'.github/workflows/*':<30}{reset}  {dim}{wf_label}{reset}")
            except GithubException:
                pass

        if not found:
            continue

        # --- Print repo header ---
        hits += 1
        print(" " * 60, end="\r")

        pushed = repo.pushed_at.strftime("%Y-%m-%d") if repo.pushed_at else "unknown"
        fork_tag = f"  {yellow}[fork]{reset}" if repo.fork else ""
        vis_colored = f"{yellow}private{reset}" if repo.private else f"{green}public{reset}"
        access_colored = (
            f"{red}admin{reset}" if access == "admin" else
            f"{yellow}write{reset}" if access == "write" else
            f"{green}read{reset}" if access == "read" else
            f"{dim}{access}{reset}"
        )
        stars = f"★ {repo.stargazers_count}" if repo.stargazers_count else "★ 0"
        open_issues = f"{repo.open_issues_count} open issue{'s' if repo.open_issues_count != 1 else ''}"

        print(f"  {bold}{white}{repo.full_name}{reset}{fork_tag}")
        print(f"    {lbl('Visibility:')}  {vis_colored}   {dim}|{reset}   {lbl('Access:')} {access_colored}   {dim}|{reset}   {lbl('Branch:')} {cyan}{repo.default_branch}{reset}")
        print(f"    {lbl('Language:  ')}  {cyan}{repo.language or '-':<20}{reset}  {yellow}{stars}{reset}   {dim}|{reset}   {dim}{open_issues}{reset}")
        print(f"    {lbl('Last push: ')}  {dim}{pushed}{reset}")
        print(f"    {lbl('Build files:')}")
        for line in found:
            print(line)
        print()

    print(" " * 60, end="\r")

    if hits == 0:
        print(f"  {warn('No build files found in any accessible repository.')}\n")
    else:
        print(f"  {success(f'Found build files in {hits} of {total} repo(s).')}\n")


def show_pat_info(client: Github, token: str) -> None:
    """Display scopes, permissions, rate limits, and account details for the current PAT."""
    print("\nFetching PAT information...\n")

    SCOPE_DESCRIPTIONS: dict[str, str] = {
        "repo":                  "Full control of private repositories",
        "repo:status":           "Access commit status",
        "repo_deployment":       "Access deployment status",
        "public_repo":           "Access public repositories",
        "repo:invite":           "Access repository invitations",
        "security_events":       "Read/write security events",
        "admin:repo_hook":       "Full control of repository hooks",
        "write:repo_hook":       "Write repository hooks",
        "read:repo_hook":        "Read repository hooks",
        "admin:org":             "Full control of orgs, teams, and projects",
        "write:org":             "Write org and team membership, projects",
        "read:org":              "Read org and team membership, projects",
        "admin:public_key":      "Full control of user public keys",
        "write:public_key":      "Write user public keys",
        "read:public_key":       "Read user public keys",
        "admin:org_hook":        "Full control of organization hooks",
        "gist":                  "Create gists",
        "notifications":         "Access notifications",
        "user":                  "Update all user data",
        "read:user":             "Read all user profile data",
        "user:email":            "Access user email addresses (read/write)",
        "user:follow":           "Follow and unfollow users",
        "project":               "Full control of user and org projects",
        "read:project":          "Read access to user and org projects",
        "delete_repo":           "Delete repositories",
        "write:packages":        "Upload packages to GitHub Package Registry",
        "read:packages":         "Download packages from GitHub Package Registry",
        "delete:packages":       "Delete packages from GitHub Package Registry",
        "admin:gpg_key":         "Full control of public user GPG keys",
        "write:gpg_key":         "Write public user GPG keys",
        "read:gpg_key":          "Read public user GPG keys",
        "codespace":             "Full control of codespaces",
        "workflow":              "Update GitHub Actions workflow files",
        "admin:ssh_signing_key": "Full control of public user SSH signing keys",
        "write:ssh_signing_key": "Write public user SSH signing keys",
        "read:ssh_signing_key":  "Read public user SSH signing keys",
    }

    try:
        # Hit /user with raw requests so we can read response headers
        resp = requests.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=10,
        )

        scopes_raw = resp.headers.get("X-OAuth-Scopes", "")
        scopes = [s.strip() for s in scopes_raw.split(",") if s.strip()]

        # Determine token type from its prefix
        if token.startswith("github_pat_"):
            token_type = "Fine-Grained PAT"
        elif token.startswith("ghp_"):
            token_type = "Classic PAT"
        elif token.startswith("gho_"):
            token_type = "OAuth Token"
        elif token.startswith("ghs_"):
            token_type = "GitHub App Installation Token"
        else:
            token_type = "Classic PAT (legacy format)"

        user = client.get_user()

        rate_resp = requests.get(
            "https://api.github.com/rate_limit",
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=10,
        )
        rate_resources = rate_resp.json().get("resources", {})

        div = f"{dim}{'─' * 60}{reset}"
        def section(title: str) -> None:
            print(div)
            print(f"  {bold}{cyan}{title}{reset}")
            print(div)

        section("Token Details")
        print(f"  {lbl('Type:         ')} {bold}{white}{token_type}{reset}")
        print(f"  {lbl('Prefix:       ')} {yellow}{token[:8]}{'*' * 10}{reset}  {dim}(first 8 chars shown){reset}")
        print()

        section("Account")
        print(f"  {lbl('Login:        ')} {bold}{green}{user.login}{reset}")
        if user.name:
            print(f"  {lbl('Name:         ')} {white}{user.name}{reset}")
        if user.email:
            print(f"  {lbl('Email:        ')} {white}{user.email}{reset}")
        print(f"  {lbl('Account type: ')} {white}{'Organization' if user.type == 'Organization' else 'Personal'}{reset}")
        if user.company:
            print(f"  {lbl('Company:      ')} {white}{user.company}{reset}")
        if user.plan:
            print(f"  {lbl('GitHub plan:  ')} {magenta}{user.plan.name}{reset}")
        print(f"  {lbl('Public repos: ')} {white}{user.public_repos}{reset}")
        print(f"  {lbl('Private repos:')} {white}{user.total_private_repos or 0}{reset}")
        print(f"  {lbl('Followers:    ')} {white}{user.followers}{reset}  {dim}|{reset}  {lbl('Following:')} {white}{user.following}{reset}")
        print()

        if token_type == "Fine-Grained PAT":
            section("Permissions  (fine-grained — per-repository)")
            print(f"  {dim}Fine-grained PATs use per-repository permissions rather than{reset}")
            print(f"  {dim}global scopes. Permissions are not enumerable via the REST API.{reset}")
            print(f"  {dim}Manage this token at: https://github.com/settings/tokens{reset}")
        else:
            section(f"Scopes  ({len(scopes)} granted)")
            if scopes:
                for scope in scopes:
                    desc = SCOPE_DESCRIPTIONS.get(scope, "")
                    print(f"  {green}•{reset} {yellow}{scope:<28}{reset}  {dim}{desc}{reset}" if desc else f"  {green}•{reset} {yellow}{scope}{reset}")
            else:
                print(f"  {dim}(none) — token has read-only access to public data only{reset}")
        print()

        section("Rate Limits")

        from datetime import datetime, timezone as tz

        def _fmt_resource(res: dict) -> str:
            remaining = res.get("remaining", "?")
            limit = res.get("limit", "?")
            reset_ts = res.get("reset")
            reset_str = (
                datetime.fromtimestamp(reset_ts, tz=tz.utc).strftime("%H:%M UTC")
                if reset_ts else "unknown"
            )
            pct = (remaining / limit) if isinstance(remaining, int) and isinstance(limit, int) and limit > 0 else 0
            color = green if pct > 0.5 else yellow if pct > 0.1 else red
            return (
                f"{color}{remaining:>6,}{reset} {dim}/{reset} {white}{limit:,}{reset} {dim}remaining  (resets {reset_str}){reset}"
                if isinstance(remaining, int) else f"{remaining} / {limit}"
            )

        for rate_label, key in [("Core API", "core"), ("Search API", "search"), ("GraphQL API", "graphql")]:
            res = rate_resources.get(key)
            if res is not None:
                print(f"  {lbl(f'{rate_label:<14}')} {_fmt_resource(res)}")
        print()

    except GithubException as exc:
        if exc.status in (403, 429):
            _handle_rate_limit(client, exc)
        else:
            msg = exc.data.get("message", str(exc))
            print(f"\n  {err(f'GitHub error ({exc.status}): {msg}')}\n")
    except requests.exceptions.ConnectionError:
        print(f"\n  {err('Network error: unable to reach GitHub. Check your connection.')}\n")


def search_actions_files(client: Github) -> None:
    """Scan all accessible repos for GitHub Actions workflow files and list them."""
    try:
        repos = list(client.get_user().get_repos(sort="updated", direction="desc"))
    except GithubException as exc:
        msg = exc.data.get("message", str(exc))
        print(f"\n  {err(f'GitHub error ({exc.status}): {msg}')}\n")
        return
    except requests.exceptions.ConnectionError:
        print(f"\n  {err('Network error: unable to reach GitHub. Check your connection.')}\n")
        return

    if not repos:
        print(f"\n  {warn('No repositories found.')}\n")
        return

    total = len(repos)
    print(f"\n{cyan}Scanning {bold}{total}{reset}{cyan} repo(s) for GitHub Actions workflow files...{reset}\n")

    total_workflows = 0
    repos_with_actions = 0

    for i, repo in enumerate(repos, start=1):
        print(f"  {dim}Checking ({i}/{total}): {repo.name} ...{reset}", end="\r", flush=True)

        try:
            contents = repo.get_contents(".github/workflows")
        except GithubException:
            continue

        if not isinstance(contents, list):
            contents = [contents]

        yml_files = sorted(
            [f for f in contents if f.name.endswith((".yml", ".yaml"))],
            key=lambda f: f.name,
        )

        if not yml_files:
            continue

        repos_with_actions += 1
        total_workflows += len(yml_files)

        print(" " * 60, end="\r")

        vis_colored = f"{yellow}private{reset}" if repo.private else f"{green}public{reset}"
        pushed = repo.pushed_at.strftime("%Y-%m-%d") if repo.pushed_at else "unknown"
        wf_count = len(yml_files)
        print(
            f"  {bold}{white}{repo.full_name}{reset}  [{vis_colored}]  "
            f"{dim}—  last push: {pushed}  —{reset}  "
            f"{magenta}{wf_count} workflow{'s' if wf_count != 1 else ''}{reset}"
        )

        for wf in yml_files:
            print(f"    {green}•{reset} {cyan}{wf.name:<40}{reset}  {dim}{wf.path}{reset}")

        print()

    print(" " * 60, end="\r")

    if repos_with_actions == 0:
        print(f"  {warn('No GitHub Actions workflow files found in any accessible repository.')}\n")
    else:
        print(
            f"  {success(f'Found {total_workflows} workflow file{chr(115) if total_workflows != 1 else str()} '
                         f'across {repos_with_actions} of {total} repo(s).')}\n"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _truncate(text: str, max_len: int) -> str:
    """Truncate text to max_len characters, appending '…' if cut."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _handle_rate_limit(client: Github, exc: GithubException) -> None:
    """Print a helpful rate-limit message including when the limit resets."""
    try:
        rate = client.get_rate_limit().core
        reset_utc = rate.reset.replace(tzinfo=timezone.utc)
        print(
            f"\n  {red}{bold}Rate limit exceeded.{reset} "
            f"{yellow}Limit resets at {reset_utc.strftime('%H:%M:%S UTC')}.{reset} "
            f"{dim}({rate.remaining} requests remaining){reset}\n"
        )
    except Exception:
        msg = exc.data.get("message", str(exc))
        print(f"\n  {err(f'GitHub error ({exc.status}): {msg}')}\n")
