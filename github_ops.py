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


def list_unprotected_repos(client: Github) -> None:
    """List all repos whose default branch has no branch protection rules enabled."""
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
    print(f"\n{cyan}Scanning {bold}{total}{reset}{cyan} repo(s) for missing branch protection...{reset}\n")

    unprotected: list[tuple] = []  # (repo, branch_name)

    for i, repo in enumerate(repos, start=1):
        print(f"  {dim}Checking ({i}/{total}): {repo.name} ...{reset}", end="\r", flush=True)

        try:
            branch = repo.get_branch(repo.default_branch)
            if not branch.protected:
                unprotected.append((repo, repo.default_branch))
        except GithubException:
            # Empty repo or no access — skip
            continue

    print(" " * 60, end="\r")

    if not unprotected:
        print(f"  {success('All repos have branch protection enabled on their default branch.')}\n")
        return

    # Column widths
    COL_NAME = 35
    COL_BRANCH = 20
    COL_VIS = 10
    COL_PUSHED = 12

    col_header = (
        f"{'Repository':<{COL_NAME}} "
        f"{'Default Branch':<{COL_BRANCH}} "
        f"{'Visibility':<{COL_VIS}} "
        f"{'Last Push':<{COL_PUSHED}}"
    )
    divider = f"{dim}{'─' * len(col_header)}{reset}"

    print(f"{bold}{cyan}{col_header}{reset}")
    print(divider)

    for repo, branch_name in unprotected:
        name = _truncate(repo.full_name, COL_NAME)
        vis_colored = f"{yellow}{'private':<{COL_VIS}}{reset}" if repo.private else f"{green}{'public':<{COL_VIS}}{reset}"
        pushed = repo.pushed_at.strftime("%Y-%m-%d") if repo.pushed_at else "unknown"

        print(
            f"{bold}{white}{name:<{COL_NAME}}{reset} "
            f"{cyan}{branch_name:<{COL_BRANCH}}{reset} "
            f"{vis_colored} "
            f"{dim}{pushed:<{COL_PUSHED}}{reset}"
        )

    print(divider)
    count = len(unprotected)
    print(
        f"\n  {red}{bold}{count} repo{'s' if count != 1 else ''}{reset}"
        f"{red} of {total} {'have' if count != 1 else 'has'} no branch protection on the default branch.{reset}\n"
    )


def search_manifest_files(client: Github) -> None:
    """Scan all accessible repos for dependency manifest and lock files and report findings."""

    MANIFEST_FILES: dict[str, str] = {
        # JavaScript / Node
        "package.json":           "npm / Node.js",
        "package-lock.json":      "npm (lockfile)",
        "yarn.lock":              "Yarn (lockfile)",
        "pnpm-lock.yaml":         "pnpm (lockfile)",
        ".npmrc":                 "npm config",
        ".nvmrc":                 "Node version pin",
        ".node-version":          "Node version pin",
        # Python
        "requirements.txt":       "pip",
        "requirements-dev.txt":   "pip (dev)",
        "Pipfile":                "Pipenv",
        "Pipfile.lock":           "Pipenv (lockfile)",
        "pyproject.toml":         "Python PEP 517",
        "poetry.lock":            "Poetry (lockfile)",
        "setup.py":               "setuptools",
        "setup.cfg":              "setuptools (cfg)",
        ".python-version":        "Python version pin",
        # Ruby
        "Gemfile":                "Bundler (Ruby)",
        "Gemfile.lock":           "Bundler (lockfile)",
        ".ruby-version":          "Ruby version pin",
        # Go
        "go.mod":                 "Go Modules",
        "go.sum":                 "Go Modules (checksum)",
        # Rust
        "Cargo.toml":             "Cargo (Rust)",
        "Cargo.lock":             "Cargo (lockfile)",
        # Java / JVM
        "pom.xml":                "Maven",
        "build.gradle":           "Gradle",
        "build.gradle.kts":       "Gradle (Kotlin DSL)",
        "gradle.properties":      "Gradle properties",
        # PHP
        "composer.json":          "Composer (PHP)",
        "composer.lock":          "Composer (lockfile)",
        # .NET / C#
        "packages.config":        "NuGet (legacy)",
        "global.json":            ".NET SDK version pin",
        # Swift / Apple
        "Package.swift":          "Swift Package Manager",
        "Package.resolved":       "Swift PM (lockfile)",
        # Dart / Flutter
        "pubspec.yaml":           "pub (Dart/Flutter)",
        "pubspec.lock":           "pub (lockfile)",
        # Elixir
        "mix.exs":                "Mix (Elixir)",
        "mix.lock":               "Mix (lockfile)",
        # Haskell
        "cabal.project":          "Cabal (Haskell)",
        "stack.yaml":             "Stack (Haskell)",
        # Terraform / Infra
        ".terraform.lock.hcl":    "Terraform provider lock",
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
    print(f"\n{cyan}Scanning {bold}{total}{reset}{cyan} repo(s) for dependency manifest files...{reset}\n")

    hits = 0
    total_files_found = 0

    for i, repo in enumerate(repos, start=1):
        print(f"  {dim}Checking ({i}/{total}): {repo.name} ...{reset}", end="\r", flush=True)

        try:
            root_contents = repo.get_contents("")
        except GithubException:
            continue

        root_names = {item.name: item for item in (root_contents if isinstance(root_contents, list) else [root_contents])}

        found_files: list[tuple[str, str, int]] = []  # (filename, label, size_bytes)
        for filename, label in MANIFEST_FILES.items():
            if filename in root_names:
                item = root_names[filename]
                found_files.append((filename, label, item.size))

        if not found_files:
            continue

        hits += 1
        total_files_found += len(found_files)
        print(" " * 60, end="\r")

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

        access_colored = (
            f"{red}admin{reset}" if access == "admin" else
            f"{yellow}write{reset}" if access == "write" else
            f"{green}read{reset}" if access == "read" else
            f"{dim}{access}{reset}"
        )

        pushed = repo.pushed_at.strftime("%Y-%m-%d") if repo.pushed_at else "unknown"
        fork_tag = f"  {yellow}[fork]{reset}" if repo.fork else ""
        vis_colored = f"{yellow}private{reset}" if repo.private else f"{green}public{reset}"
        stars = f"★ {repo.stargazers_count}" if repo.stargazers_count else "★ 0"

        # Group files by ecosystem for a cleaner display
        ecosystems: dict[str, list[tuple[str, int]]] = {}
        for filename, label, size in found_files:
            ecosystem = label.split(" (")[0].split(" /")[0].strip()
            ecosystems.setdefault(ecosystem, []).append((filename, size))

        print(f"  {bold}{white}{repo.full_name}{reset}{fork_tag}")
        print(f"    {lbl('URL:       ')}  {dim}{repo.html_url}{reset}")
        print(f"    {lbl('Visibility:')}  {vis_colored}   {dim}|{reset}   {lbl('Access:')} {access_colored}   {dim}|{reset}   {lbl('Branch:')} {cyan}{repo.default_branch}{reset}")
        print(f"    {lbl('Language:  ')}  {cyan}{repo.language or '-':<20}{reset}  {yellow}{stars}{reset}   {dim}|{reset}   {lbl('Last push:')} {dim}{pushed}{reset}")
        print(f"    {lbl('Manifests: ')}  {dim}{len(found_files)} file{'s' if len(found_files) != 1 else ''} found{reset}")

        for filename, label, size in sorted(found_files, key=lambda x: x[0]):
            is_lock = "lock" in label.lower() or filename.endswith(".lock") or filename.endswith(".resolved")
            file_color = dim if is_lock else cyan
            size_str = f"{size:,} B" if size < 1024 else f"{size // 1024:,} KB"
            lock_badge = f"  {dim}[lock]{reset}" if is_lock else ""
            print(f"      {file_color}{filename:<35}{reset}  {dim}{label:<30}{reset}  {dim}{size_str:>8}{reset}{lock_badge}")

        print()

    print(" " * 60, end="\r")

    if hits == 0:
        print(f"  {warn('No manifest files found in any accessible repository.')}\n")
    else:
        print(
            f"  {success(f'Found {total_files_found} manifest file{chr(115) if total_files_found != 1 else str()} '
                         f'across {hits} of {total} repo(s).')}\n"
        )


def edit_manifest_file(client: Github) -> None:
    """Select a repo, pick a manifest file, edit it in $EDITOR, and commit changes to GitHub."""

    MANIFEST_FILES: dict[str, str] = {
        # JavaScript / Node
        "package.json":           "npm / Node.js",
        "package-lock.json":      "npm (lockfile)",
        "yarn.lock":              "Yarn (lockfile)",
        "pnpm-lock.yaml":         "pnpm (lockfile)",
        ".npmrc":                 "npm config",
        ".nvmrc":                 "Node version pin",
        ".node-version":          "Node version pin",
        # Python
        "requirements.txt":       "pip",
        "requirements-dev.txt":   "pip (dev)",
        "Pipfile":                "Pipenv",
        "Pipfile.lock":           "Pipenv (lockfile)",
        "pyproject.toml":         "Python PEP 517",
        "poetry.lock":            "Poetry (lockfile)",
        "setup.py":               "setuptools",
        "setup.cfg":              "setuptools (cfg)",
        ".python-version":        "Python version pin",
        # Ruby
        "Gemfile":                "Bundler (Ruby)",
        "Gemfile.lock":           "Bundler (lockfile)",
        ".ruby-version":          "Ruby version pin",
        # Go
        "go.mod":                 "Go Modules",
        "go.sum":                 "Go Modules (checksum)",
        # Rust
        "Cargo.toml":             "Cargo (Rust)",
        "Cargo.lock":             "Cargo (lockfile)",
        # Java / JVM
        "pom.xml":                "Maven",
        "build.gradle":           "Gradle",
        "build.gradle.kts":       "Gradle (Kotlin DSL)",
        "gradle.properties":      "Gradle properties",
        # PHP
        "composer.json":          "Composer (PHP)",
        "composer.lock":          "Composer (lockfile)",
        # .NET / C#
        "packages.config":        "NuGet (legacy)",
        "global.json":            ".NET SDK version pin",
        # Swift / Apple
        "Package.swift":          "Swift Package Manager",
        "Package.resolved":       "Swift PM (lockfile)",
        # Dart / Flutter
        "pubspec.yaml":           "pub (Dart/Flutter)",
        "pubspec.lock":           "pub (lockfile)",
        # Elixir
        "mix.exs":                "Mix (Elixir)",
        "mix.lock":               "Mix (lockfile)",
        # Haskell
        "cabal.project":          "Cabal (Haskell)",
        "stack.yaml":             "Stack (Haskell)",
        # Terraform / Infra
        ".terraform.lock.hcl":    "Terraform provider lock",
    }

    print(f"\n{cyan}Edit Manifest File{reset}\n")

    # --- Phase 1: Repo selection (only repos with manifest files) ---
    try:
        all_repos = list(client.get_user().get_repos(sort="updated", direction="desc"))
    except GithubException as exc:
        msg = exc.data.get("message", str(exc))
        print(f"\n  {err(f'GitHub error ({exc.status}): {msg}')}\n")
        return
    except requests.exceptions.ConnectionError:
        print(f"\n  {err('Network error: unable to reach GitHub. Check your connection.')}\n")
        return

    if not all_repos:
        print(f"\n  {warn('No repositories found.')}\n")
        return

    print(f"  {dim}Scanning {len(all_repos)} repositories for manifest files...{reset}")

    repos_with_manifests: list[tuple] = []
    for repo in all_repos:
        try:
            root_contents = repo.get_contents("")
        except GithubException:
            continue
        except requests.exceptions.ConnectionError:
            print(f"\n  {err('Network error: unable to reach GitHub. Check your connection.')}\n")
            return
        items = root_contents if isinstance(root_contents, list) else [root_contents]
        root_map = {item.name: item for item in items}
        manifests = [
            (filename, label, root_map[filename])
            for filename, label in MANIFEST_FILES.items()
            if filename in root_map
        ]
        if manifests:
            repos_with_manifests.append((repo, manifests))

    if not repos_with_manifests:
        print(f"\n  {warn('No repositories with manifest files found.')}\n")
        return

    print(f"\n  {dim}{'#':<4}{'Repository':<40}{'Visibility':<12}{'Language'}{reset}")
    print(f"  {dim}{'─' * 70}{reset}")
    for i, (repo, _) in enumerate(repos_with_manifests, start=1):
        vis = f"{yellow}private{reset}" if repo.private else f"{green}public{reset}"
        lang = repo.language or ""
        print(f"  {dim}{i:<4}{reset}{bold}{repo.full_name:<40}{reset}{vis:<20}{cyan}{lang}{reset}")

    print()
    raw = input(f"  {bold}Select repo number{reset} {dim}(or 0 to cancel):{reset} ").strip()
    if not raw.isdigit():
        print(f"\n  {err('Invalid input. Enter a number.')}\n")
        return
    choice = int(raw)
    if choice == 0:
        print(f"\n  {muted('Cancelled.')}\n")
        return
    if choice < 1 or choice > len(repos_with_manifests):
        print(f"\n  {err(f'Selection out of range. Enter 1–{len(repos_with_manifests)}.')}\n")
        return

    selected_repo, found_manifests = repos_with_manifests[choice - 1]

    # --- Phase 2: Manifest discovery (already scanned) ---
    print(f"\n  {dim}Found {len(found_manifests)} manifest file(s) in {bold}{selected_repo.full_name}{reset}{dim}.{reset}")

    # --- Phase 3: File selection ---
    if len(found_manifests) == 1:
        chosen_filename, chosen_label, chosen_item = found_manifests[0]
        print(f"\n  {success('Found 1 manifest file:')} {cyan}{chosen_filename}{reset}  {dim}({chosen_label}){reset}")
        print(f"  {dim}Auto-selected.{reset}")
    else:
        print(f"\n  {bold}{cyan}Manifest files found:{reset}\n")
        print(f"  {dim}{'#':<4}{'File':<40}{'Ecosystem':<32}{'Size'}{reset}")
        print(f"  {dim}{'─' * 70}{reset}")
        for i, (filename, label, item) in enumerate(found_manifests, start=1):
            size = item.size
            size_str = f"{size:,} B" if size < 1024 else f"{size // 1024:,} KB"
            print(f"  {dim}{i:<4}{reset}{cyan}{filename:<40}{reset}{dim}{label:<32}{size_str}{reset}")

        print()
        raw2 = input(f"  {bold}Select file number{reset} {dim}(or 0 to cancel):{reset} ").strip()
        if not raw2.isdigit():
            print(f"\n  {err('Invalid input. Enter a number.')}\n")
            return
        choice2 = int(raw2)
        if choice2 == 0:
            print(f"\n  {muted('Cancelled.')}\n")
            return
        if choice2 < 1 or choice2 > len(found_manifests):
            print(f"\n  {err(f'Selection out of range. Enter 1–{len(found_manifests)}.')}\n")
            return
        chosen_filename, chosen_label, chosen_item = found_manifests[choice2 - 1]

    # --- Phase 4: Read file content ---
    print(f"\n  {dim}Fetching {cyan}{chosen_filename}{reset}{dim}...{reset}")
    try:
        file_obj = selected_repo.get_contents(chosen_filename)
    except GithubException as exc:
        msg = exc.data.get("message", str(exc))
        print(f"\n  {err(f'GitHub error ({exc.status}): {msg}')}\n")
        return
    except requests.exceptions.ConnectionError:
        print(f"\n  {err('Network error: unable to reach GitHub. Check your connection.')}\n")
        return

    original_content = file_obj.decoded_content.decode("utf-8")
    sha = file_obj.sha

    # --- Phase 5: Display with line numbers ---
    lines = original_content.splitlines()
    line_count = len(lines)
    size_bytes = len(original_content.encode("utf-8"))
    print(f"\n  {bold}{cyan}{chosen_filename}{reset}  {dim}({line_count} lines, {size_bytes:,} bytes){reset}\n")
    num_width = len(str(line_count))
    for i, line in enumerate(lines, start=1):
        print(f"  {dim}{i:{num_width}}{reset}  {line}")
    print()

    # --- Phase 6: Open in $EDITOR ---
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "nano"
    if not shutil.which(editor):
        msg = f"Editor '{editor}' not found on PATH. Set $EDITOR to a valid editor."
        print(f"\n  {err(msg)}\n")
        return

    print(f"  {dim}Opening {chosen_filename} in {bold}{editor}{reset}{dim}...{reset}")
    print(f"  {dim}Save and quit the editor when done.{reset}\n")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=f"_{chosen_filename}",
            prefix="bamf_edit_",
            delete=False,
            encoding="utf-8",
        ) as tmp:
            tmp.write(original_content)
            tmp_path = tmp.name

        result = subprocess.run([editor, tmp_path])
        if result.returncode != 0:
            print(f"\n  {warn(f'Editor exited with code {result.returncode}. Treating as cancelled.')}\n")
            return

        with open(tmp_path, "r", encoding="utf-8") as f:
            new_content = f.read()
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    # --- Phase 7: Diff preview ---
    if new_content == original_content:
        print(f"  {muted('No changes detected. File is unchanged. Nothing to commit.')}\n")
        return

    original_lines = original_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    diff = list(difflib.unified_diff(
        original_lines,
        new_lines,
        fromfile=f"a/{chosen_filename}",
        tofile=f"b/{chosen_filename}",
        lineterm="",
    ))

    print(f"  {bold}{cyan}Changes:{reset}\n")
    for line in diff:
        if line.startswith("+++") or line.startswith("---"):
            print(f"  {dim}{line}{reset}")
        elif line.startswith("+"):
            print(f"  {green}{line}{reset}")
        elif line.startswith("-"):
            print(f"  {red}{line}{reset}")
        elif line.startswith("@@"):
            print(f"  {cyan}{line}{reset}")
        else:
            print(f"  {dim}{line}{reset}")
    print()

    added = sum(1 for ln in diff if ln.startswith("+") and not ln.startswith("+++"))
    removed = sum(1 for ln in diff if ln.startswith("-") and not ln.startswith("---"))
    print(f"  {green}+{added} line{'s' if added != 1 else ''}{reset}  {red}-{removed} line{'s' if removed != 1 else ''}{reset}\n")

    # --- Phase 8: Confirm and commit message ---
    confirm = input(f"  {bold}Save and commit to GitHub?{reset} {dim}[y/N]:{reset} ").strip().lower()
    if confirm not in ("y", "yes"):
        print(f"\n  {muted('Cancelled. No changes committed.')}\n")
        return

    default_msg = f"chore: update {chosen_filename} via bamf"
    raw_msg = input(f"  {bold}Commit message{reset} {dim}[{default_msg}]:{reset} ").strip()
    commit_message = raw_msg if raw_msg else default_msg

    # --- Phase 9: Commit to GitHub ---
    print(f"\n  {dim}Committing to {selected_repo.default_branch}...{reset}")
    try:
        selected_repo.update_file(
            path=chosen_filename,
            message=commit_message,
            content=new_content,
            sha=sha,
            branch=selected_repo.default_branch,
        )
        print(f"\n  {success('File committed successfully!')}")
        print(f"  {lbl('Repository:')} {bold}{selected_repo.full_name}{reset}")
        print(f"  {lbl('File:      ')} {cyan}{chosen_filename}{reset}")
        print(f"  {lbl('Branch:    ')} {cyan}{selected_repo.default_branch}{reset}")
        print(f"  {lbl('Message:   ')} {dim}{commit_message}{reset}\n")
    except GithubException as exc:
        if exc.status == 409:
            print(f"\n  {err('Conflict: the file was modified on GitHub since you fetched it. Re-run to get the latest version.')}\n")
        elif exc.status in (401, 403):
            print(f"\n  {err('Permission denied. Your PAT may not have write access to this repository.')}\n")
        else:
            msg = exc.data.get("message", str(exc))
            print(f"\n  {err(f'GitHub error ({exc.status}): {msg}')}\n")
    except requests.exceptions.ConnectionError:
        print(f"\n  {err('Network error: unable to reach GitHub. Check your connection.')}\n")


def scan_secrets(client: Github, token: str) -> None:
    """Shallow-clone all accessible repos and scan them for leaked secrets using gitleaks."""

    if not shutil.which("gitleaks"):
        print(f"\n  {err('gitleaks is not installed or not in PATH.')}")
        print(f"  {dim}macOS:   brew install gitleaks{reset}")
        print(f"  {dim}Linux:   https://github.com/gitleaks/gitleaks/releases{reset}\n")
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

    total = len(repos)
    print(f"\n{cyan}Scanning {bold}{total}{reset}{cyan} repo(s) for secrets using gitleaks...{reset}")
    print(f"  {dim}(shallow clone — scans latest commit of each repo){reset}\n")

    findings_by_repo: dict[str, list[dict]] = {}
    clone_errors: list[str] = []
    repo_lookup = {r.full_name: r for r in repos}

    with tempfile.TemporaryDirectory(prefix="bamf_secrets_") as tmpdir:
        for i, repo in enumerate(repos, start=1):
            repo_dir = os.path.join(tmpdir, repo.name)
            clone_url = f"https://x-access-token:{token}@github.com/{repo.full_name}.git"

            print(f"  {dim}[{i}/{total}] Cloning  {repo.name} ...{reset}", end="\r", flush=True)

            clone_result = subprocess.run(
                ["git", "clone", "--depth=1", "--quiet", clone_url, repo_dir],
                capture_output=True, text=True,
            )
            if clone_result.returncode != 0:
                clone_errors.append(repo.name)
                continue

            print(f"  {dim}[{i}/{total}] Scanning {repo.name} ...{reset}", end="\r", flush=True)

            report_path = os.path.join(tmpdir, f"{repo.name}.json")
            subprocess.run(
                [
                    "gitleaks", "detect",
                    "--source", repo_dir,
                    "--report-format", "json",
                    "--report-path", report_path,
                    "--no-banner",
                ],
                capture_output=True, text=True,
            )

            if os.path.exists(report_path):
                try:
                    raw = open(report_path).read().strip()
                    if raw and raw != "null":
                        data = json.loads(raw)
                        if isinstance(data, list) and data:
                            findings_by_repo[repo.full_name] = data
                except (json.JSONDecodeError, OSError):
                    pass

    print(" " * 70, end="\r")

    if not findings_by_repo:
        print(f"  {success('No secrets detected in any repository.')}")
        if clone_errors:
            skipped = ", ".join(clone_errors[:5]) + ("…" if len(clone_errors) > 5 else "")
            print(f"  {warn(f'{len(clone_errors)} repo(s) could not be cloned (skipped): {skipped}')}")
        print()
        return

    total_findings = sum(len(f) for f in findings_by_repo.values())
    repos_hit = len(findings_by_repo)
    print(
        f"  {red}{bold}[!] {total_findings} potential secret{'s' if total_findings != 1 else ''} "
        f"found across {repos_hit} repo{'s' if repos_hit != 1 else ''}:{reset}\n"
    )

    for repo_name, findings in findings_by_repo.items():
        repo_obj = repo_lookup.get(repo_name)
        vis_str = ""
        if repo_obj:
            vis_str = f"  [{yellow}private{reset}]" if repo_obj.private else f"  [{green}public{reset}]"

        print(f"  {bold}{red}{repo_name}{reset}{vis_str}  {dim}{len(findings)} finding{'s' if len(findings) != 1 else ''}{reset}")
        if repo_obj:
            print(f"    {lbl('URL:')}  {dim}{repo_obj.html_url}{reset}")

        for finding in findings:
            rule_id     = finding.get("RuleID", "unknown")
            description = finding.get("Description") or rule_id
            file_path   = finding.get("File", "")
            start_line  = finding.get("StartLine", "")
            secret_raw  = finding.get("Secret", "")
            commit_hash = (finding.get("Commit") or "")[:8]
            author      = finding.get("Author", "")

            print(f"\n    {red}>{reset} {bold}{description}{reset}  {dim}[{rule_id}]{reset}")
            if file_path:
                loc = f"{file_path}:{start_line}" if start_line else file_path
                print(f"      {lbl('File:   ')} {cyan}{loc}{reset}")
            if secret_raw:
                print(f"      {lbl('Secret: ')} {yellow}{secret_raw}{reset}")
            if commit_hash:
                print(f"      {lbl('Commit: ')} {dim}{commit_hash}{reset}")
            if author:
                print(f"      {lbl('Author: ')} {dim}{author}{reset}")

        print()

    if clone_errors:
        skipped = ", ".join(clone_errors[:5]) + ("…" if len(clone_errors) > 5 else "")
        print(f"  {warn(f'{len(clone_errors)} repo(s) skipped (clone error): {skipped}')}\n")
    else:
        print()


def audit_security_posture(client: Github) -> None:
    """Check which GitHub security features are enabled across all accessible repos."""

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
    print(f"\n{cyan}Auditing security posture across {bold}{total}{reset}{cyan} repo(s)...{reset}\n")

    # counters: feature → repos with it disabled
    disabled: dict[str, int] = {
        "Dependabot alerts": 0,
        "Dependabot updates": 0,
        "Secret scanning": 0,
        "Push protection": 0,
    }
    repos_with_gaps = 0

    def _status(obj, attr: str) -> str:
        if obj is None:
            return "n/a"
        val = getattr(obj, attr, None)
        if val is None:
            return "n/a"
        return getattr(val, "status", "n/a")

    def _fmt(status: str) -> str:
        if status == "enabled":
            return f"{green}enabled {reset}"
        if status in ("disabled", "not_set"):
            return f"{red}disabled{reset}"
        return f"{dim}n/a     {reset}"

    for i, repo in enumerate(repos, start=1):
        print(f"  {dim}Checking ({i}/{total}): {repo.name} ...{reset}", end="\r", flush=True)

        try:
            dep_alerts = repo.get_vulnerability_alert()
        except GithubException:
            dep_alerts = None

        saa = repo.security_and_analysis

        dep_updates = _status(saa, "dependabot_security_updates")
        secret_scan = _status(saa, "secret_scanning")
        push_prot   = _status(saa, "secret_scanning_push_protection")

        gap = (
            dep_alerts is False
            or dep_updates == "disabled"
            or secret_scan == "disabled"
            or push_prot == "disabled"
        )
        if gap:
            repos_with_gaps += 1

        if dep_alerts is False:
            disabled["Dependabot alerts"] += 1
        if dep_updates == "disabled":
            disabled["Dependabot updates"] += 1
        if secret_scan == "disabled":
            disabled["Secret scanning"] += 1
        if push_prot == "disabled":
            disabled["Push protection"] += 1

        print(" " * 60, end="\r")
        vis = f"{yellow}private{reset}" if repo.private else f"{green}public {reset}"
        dep_alerts_fmt = (
            f"{green}enabled {reset}" if dep_alerts is True
            else f"{red}disabled{reset}" if dep_alerts is False
            else f"{dim}n/a     {reset}"
        )

        print(f"  {bold}{white}{repo.full_name}{reset}  [{vis}]")
        print(f"    {lbl('Dependabot alerts: ')}  {dep_alerts_fmt}    {lbl('Dependabot updates:')}  {_fmt(dep_updates)}")
        print(f"    {lbl('Secret scanning:   ')}  {_fmt(secret_scan)}    {lbl('Push protection:   ')}  {_fmt(push_prot)}")
        print()

    summary_parts = [f"{v} repo(s) missing {k}" for k, v in disabled.items() if v > 0]
    if not summary_parts:
        print(f"  {success('All repos have all security features enabled.')}\n")
    else:
        print(f"  {warn(f'{repos_with_gaps} of {total} repo(s) have security gaps:')}")
        for part in summary_parts:
            print(f"    {dim}- {part}{reset}")
        print()


def list_dependabot_alerts(client: Github) -> None:
    """Fetch open Dependabot CVE alerts across all accessible repos, grouped by severity."""

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
    print(f"\n{cyan}Checking Dependabot alerts across {bold}{total}{reset}{cyan} repo(s)...{reset}\n")

    sev_color = {"critical": red, "high": red, "medium": yellow, "low": cyan}
    total_counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    repos_hit = 0

    for i, repo in enumerate(repos, start=1):
        print(f"  {dim}Checking ({i}/{total}): {repo.name} ...{reset}", end="\r", flush=True)

        try:
            alerts = list(repo.get_dependabot_alerts(state="open"))
        except GithubException as exc:
            if exc.status in (403, 404):
                continue
            if exc.status in (429,):
                _handle_rate_limit(client, exc)
                return
            continue

        if not alerts:
            continue

        repos_hit += 1
        print(" " * 60, end="\r")

        by_sev: dict[str, list] = {"critical": [], "high": [], "medium": [], "low": []}
        for alert in alerts:
            sev = (alert.security_advisory.severity or "low").lower()
            by_sev.setdefault(sev, []).append(alert)
            if sev in total_counts:
                total_counts[sev] += 1

        vis = f"{yellow}private{reset}" if repo.private else f"{green}public{reset}"
        print(f"  {bold}{white}{repo.full_name}{reset}  [{vis}]  {dim}{len(alerts)} alert{'s' if len(alerts) != 1 else ''}{reset}")
        print(f"    {lbl('URL:')}  {dim}{repo.html_url}{reset}")

        for sev in ("critical", "high", "medium", "low"):
            if not by_sev.get(sev):
                continue
            col = sev_color.get(sev, dim)
            for alert in by_sev[sev]:
                pkg   = alert.dependency.package.name if alert.dependency and alert.dependency.package else "unknown"
                mpath = alert.dependency.manifest_path if alert.dependency else ""
                cve   = alert.security_advisory.cve_id or ""
                summary = _truncate(alert.security_advisory.summary or "", 70)
                badge = f"{col}[{sev.upper():8}]{reset}"
                print(f"    {badge}  {bold}{pkg}{reset}  {dim}{cve}{reset}")
                print(f"             {dim}{summary}{reset}")
                if mpath:
                    print(f"             {lbl('Manifest:')} {dim}{mpath}{reset}")
        print()

    print(" " * 60, end="\r")

    if repos_hit == 0:
        print(f"  {success('No open Dependabot alerts found.')}\n")
    else:
        parts = [f"{v} {k}" for k, v in total_counts.items() if v > 0]
        print(f"  {warn(f'Open alerts: {", ".join(parts)} — across {repos_hit} of {total} repo(s).')}\n")


def audit_branch_protection(client: Github) -> None:
    """Show detailed branch protection rules for every repo, flagging dangerous configs."""

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
    print(f"\n{cyan}Auditing branch protection across {bold}{total}{reset}{cyan} repo(s)...{reset}\n")

    unprotected = 0
    flagged = 0

    for i, repo in enumerate(repos, start=1):
        print(f"  {dim}Checking ({i}/{total}): {repo.name} ...{reset}", end="\r", flush=True)

        try:
            branch = repo.get_branch(repo.default_branch)
        except GithubException:
            continue

        print(" " * 60, end="\r")
        vis = f"{yellow}private{reset}" if repo.private else f"{green}public{reset}"
        print(f"  {bold}{white}{repo.full_name}{reset}  [{vis}]  {dim}branch: {repo.default_branch}{reset}")

        if not branch.protected:
            unprotected += 1
            print(f"    {red}[!] No branch protection enabled{reset}\n")
            continue

        try:
            prot = branch.get_protection()
        except GithubException:
            print(f"    {dim}(protection details unavailable — insufficient access){reset}\n")
            continue

        issues: list[str] = []

        # Enforce admins
        try:
            enforce = prot.enforce_admins
            enforce_on = getattr(enforce, "enabled", False) if enforce else False
        except Exception:
            enforce_on = False
        enforce_fmt = f"{green}yes{reset}" if enforce_on else f"{red}no{reset}"
        if not enforce_on:
            issues.append("admins can bypass rules")

        # Required PR reviews
        rpr = prot.required_pull_request_reviews
        if rpr:
            approvals = getattr(rpr, "required_approving_review_count", 0) or 0
            dismiss   = getattr(rpr, "dismiss_stale_reviews", False)
            codeowner = getattr(rpr, "require_code_owner_reviews", False)
            apr_fmt   = f"{green}{approvals}{reset}" if approvals >= 1 else f"{red}{approvals}{reset}"
            if approvals == 0:
                issues.append("0 required approvals")
        else:
            approvals = 0
            dismiss   = False
            codeowner = False
            apr_fmt   = f"{red}none{reset}"
            issues.append("no PR review requirement")

        # Status checks
        rsc = prot.required_status_checks
        if rsc:
            strict_fmt = f"{green}yes{reset}" if rsc.strict else f"{yellow}no{reset}"
            checks_fmt = f"{dim}{len(rsc.contexts)} check(s){reset}"
        else:
            strict_fmt = f"{dim}n/a{reset}"
            checks_fmt = f"{dim}none{reset}"

        # Force push / deletions
        try:
            fp = prot.allow_force_pushes
            fp_allowed = getattr(fp, "enabled", False) if fp else False
        except Exception:
            fp_allowed = False
        try:
            ad = prot.allow_deletions
            del_allowed = getattr(ad, "enabled", False) if ad else False
        except Exception:
            del_allowed = False

        fp_fmt  = f"{red}allowed{reset}" if fp_allowed else f"{green}blocked{reset}"
        del_fmt = f"{red}allowed{reset}" if del_allowed else f"{green}blocked{reset}"
        if fp_allowed:
            issues.append("force pushes allowed")
        if del_allowed:
            issues.append("branch deletions allowed")

        if issues:
            flagged += 1

        print(f"    {lbl('Enforce admins:    ')}  {enforce_fmt}    {lbl('Required approvals:')}  {apr_fmt}")
        print(f"    {lbl('Dismiss stale:     ')}  {'yes' if dismiss else 'no':3}        {lbl('Require CODEOWNERS:')}  {'yes' if codeowner else 'no'}")
        print(f"    {lbl('Status checks:     ')}  {checks_fmt}  {lbl('Up-to-date branch: ')}  {strict_fmt}")
        print(f"    {lbl('Force pushes:      ')}  {fp_fmt}    {lbl('Branch deletions:  ')}  {del_fmt}")
        if issues:
            print(f"    {yellow}Issues: {', '.join(issues)}{reset}")
        print()

    print(" " * 60, end="\r")
    print(f"  {success(f'{total - unprotected} of {total} repo(s) have branch protection.')}")
    if flagged:
        print(f"  {warn(f'{flagged} protected repo(s) have configuration issues.')}")
    if unprotected:
        print(f"  {warn(f'{unprotected} repo(s) have no protection at all.')}")
    print()


def audit_webhooks(client: Github) -> None:
    """List all webhooks across repos and flag insecure configurations."""

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
    print(f"\n{cyan}Scanning webhooks across {bold}{total}{reset}{cyan} repo(s)...{reset}\n")

    total_hooks = 0
    flagged_hooks = 0
    repos_hit = 0

    for i, repo in enumerate(repos, start=1):
        print(f"  {dim}Checking ({i}/{total}): {repo.name} ...{reset}", end="\r", flush=True)

        try:
            hooks = list(repo.get_hooks())
        except GithubException as exc:
            if exc.status in (403, 404):
                continue
            continue

        if not hooks:
            continue

        repos_hit += 1
        total_hooks += len(hooks)
        print(" " * 60, end="\r")

        vis = f"{yellow}private{reset}" if repo.private else f"{green}public{reset}"
        print(f"  {bold}{white}{repo.full_name}{reset}  [{vis}]  {dim}{len(hooks)} webhook{'s' if len(hooks) != 1 else ''}{reset}")

        for hook in hooks:
            cfg         = hook.config or {}
            url         = cfg.get("url", "(no url)")
            insecure    = cfg.get("insecure_ssl", "0") == "1"
            has_secret  = bool(cfg.get("secret"))
            active      = hook.active
            updated     = hook.updated_at.strftime("%Y-%m-%d") if hook.updated_at else "unknown"
            events_str  = ", ".join(sorted(hook.events)[:5])
            if len(hook.events) > 5:
                events_str += f" +{len(hook.events) - 5} more"

            flags: list[str] = []
            if not url.startswith("https://"):
                flags.append(f"{red}[HTTP — unencrypted]{reset}")
                flagged_hooks += 1
            if insecure:
                flags.append(f"{red}[SSL not verified]{reset}")
                flagged_hooks += 1
            if not has_secret:
                flags.append(f"{yellow}[no HMAC secret]{reset}")
                flagged_hooks += 1
            if not active:
                flags.append(f"{dim}[inactive]{reset}")

            url_col = red if (not url.startswith("https://") or insecure) else cyan
            print(f"\n    {url_col}{_truncate(url, 70)}{reset}")
            print(f"    {lbl('Active:')} {'yes' if active else f'{dim}no{reset}'}   {lbl('Updated:')} {dim}{updated}{reset}   {lbl('Events:')} {dim}{events_str}{reset}")
            if flags:
                print(f"    {' '.join(flags)}")

        print()

    print(" " * 60, end="\r")

    if repos_hit == 0:
        print(f"  {success('No webhooks found in any repository.')}\n")
    else:
        print(f"  {success(f'Found {total_hooks} webhook(s) across {repos_hit} of {total} repo(s).')}")
        if flagged_hooks:
            print(f"  {warn(f'{flagged_hooks} flag(s) raised (HTTP, no SSL verification, or no HMAC secret).')}")
        print()


def audit_collaborators(client: Github) -> None:
    """List outside collaborators and pending invitations per repo, flagging elevated access."""
    from datetime import datetime, timezone as _tz

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
    print(f"\n{cyan}Auditing collaborator access across {bold}{total}{reset}{cyan} repo(s)...{reset}\n")

    now = datetime.now(tz=_tz.utc)
    total_outside = 0
    elevated_count = 0
    repos_hit = 0

    for i, repo in enumerate(repos, start=1):
        print(f"  {dim}Checking ({i}/{total}): {repo.name} ...{reset}", end="\r", flush=True)

        try:
            outside = list(repo.get_collaborators(affiliation="outside"))
        except GithubException as exc:
            if exc.status in (403, 404):
                continue
            continue

        try:
            invites = list(repo.get_pending_invitations())
        except GithubException:
            invites = []

        if not outside and not invites:
            continue

        repos_hit += 1
        total_outside += len(outside)
        print(" " * 60, end="\r")

        vis = f"{yellow}private{reset}" if repo.private else f"{green}public{reset}"
        print(f"  {bold}{white}{repo.full_name}{reset}  [{vis}]")

        if outside:
            print(f"    {lbl('Outside collaborators:')}  {dim}{len(outside)}{reset}")
            for user in outside:
                try:
                    perm = repo.get_collaborator_permission(user)
                except GithubException:
                    perm = "unknown"

                if perm in ("admin", "write"):
                    perm_fmt = f"{red}{perm}{reset}"
                    elevated_count += 1
                elif perm == "read":
                    perm_fmt = f"{green}{perm}{reset}"
                else:
                    perm_fmt = f"{dim}{perm}{reset}"

                print(f"      {bold}{user.login}{reset}  {lbl('perm:')} {perm_fmt}  {dim}{user.html_url}{reset}")

        if invites:
            print(f"    {lbl('Pending invitations:')}  {dim}{len(invites)}{reset}")
            for inv in invites:
                invitee = inv.invitee.login if inv.invitee else "(unknown)"
                role    = inv.role or "unknown"
                age_days = (now - inv.created_at.replace(tzinfo=_tz.utc)).days if inv.created_at else 0
                stale   = age_days > 30
                age_fmt = f"{yellow}{age_days}d old{reset}" if stale else f"{dim}{age_days}d old{reset}"
                role_fmt = f"{red}{role}{reset}" if role in ("admin", "write") else f"{dim}{role}{reset}"
                stale_tag = f"  {yellow}[stale]{reset}" if stale else ""
                print(f"      {bold}{invitee}{reset}  {lbl('role:')} {role_fmt}  {age_fmt}{stale_tag}")

        print()

    print(" " * 60, end="\r")

    if repos_hit == 0:
        print(f"  {success('No outside collaborators or pending invitations found.')}\n")
    else:
        print(f"  {success(f'Found {total_outside} outside collaborator(s) across {repos_hit} of {total} repo(s).')}")
        if elevated_count:
            print(f"  {warn(f'{elevated_count} outside collaborator(s) have admin or write access.')}")
        print()


def audit_deploy_keys(client: Github) -> None:
    """List all deploy keys across repos, flagging write-access and unused keys."""
    from datetime import datetime, timezone as _tz

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
    print(f"\n{cyan}Auditing deploy keys across {bold}{total}{reset}{cyan} repo(s)...{reset}\n")

    now = datetime.now(tz=_tz.utc)
    total_keys = 0
    flagged_keys = 0
    repos_hit = 0

    for i, repo in enumerate(repos, start=1):
        print(f"  {dim}Checking ({i}/{total}): {repo.name} ...{reset}", end="\r", flush=True)

        try:
            keys = list(repo.get_keys())
        except GithubException as exc:
            if exc.status in (403, 404):
                continue
            continue

        if not keys:
            continue

        repos_hit += 1
        total_keys += len(keys)
        print(" " * 60, end="\r")

        vis = f"{yellow}private{reset}" if repo.private else f"{green}public{reset}"
        print(f"  {bold}{white}{repo.full_name}{reset}  [{vis}]  {dim}{len(keys)} key{'s' if len(keys) != 1 else ''}{reset}")

        for key in keys:
            read_only   = getattr(key, "read_only", True)
            verified    = getattr(key, "verified", False)
            created_at  = getattr(key, "created_at", None)
            last_used   = getattr(key, "last_used_at", None)
            title       = key.title or "(untitled)"

            age_days = (now - created_at.replace(tzinfo=_tz.utc)).days if created_at else 0
            created_fmt = created_at.strftime("%Y-%m-%d") if created_at else "unknown"

            flags: list[str] = []
            if not read_only:
                flags.append(f"{red}[write access]{reset}")
                flagged_keys += 1
            if last_used is None:
                flags.append(f"{yellow}[never used]{reset}")
                flagged_keys += 1
            elif age_days > 365:
                last_used_days = (now - last_used.replace(tzinfo=_tz.utc)).days if last_used else age_days
                if last_used_days > 180:
                    flags.append(f"{yellow}[inactive {last_used_days}d]{reset}")
                    flagged_keys += 1

            access_fmt = f"{red}read/write{reset}" if not read_only else f"{green}read-only {reset}"
            verif_fmt  = f"{green}verified{reset}" if verified else f"{dim}unverified{reset}"
            print(f"\n    {bold}{title}{reset}")
            print(f"    {lbl('Access:')} {access_fmt}   {lbl('Verified:')} {verif_fmt}   {lbl('Created:')} {dim}{created_fmt}{reset}")
            if flags:
                print(f"    {' '.join(flags)}")

        print()

    print(" " * 60, end="\r")

    if repos_hit == 0:
        print(f"  {success('No deploy keys found in any repository.')}\n")
    else:
        print(f"  {success(f'Found {total_keys} deploy key(s) across {repos_hit} of {total} repo(s).')}")
        if flagged_keys:
            print(f"  {warn(f'{flagged_keys} flag(s) raised (write access, never used, or long inactive).')}")
        print()


def audit_actions_secrets(client: Github) -> None:
    """List GitHub Actions secrets across all repos (names only; values are never exposed)."""
    from datetime import datetime, timezone as _tz

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
    print(f"\n{cyan}Auditing Actions secrets across {bold}{total}{reset}{cyan} repo(s)...{reset}")
    print(f"  {dim}(secret names only — values are never exposed by the GitHub API){reset}\n")

    now = datetime.now(tz=_tz.utc)
    total_secrets = 0
    stale_count = 0
    repos_hit = 0

    for i, repo in enumerate(repos, start=1):
        print(f"  {dim}Checking ({i}/{total}): {repo.name} ...{reset}", end="\r", flush=True)

        try:
            secrets = list(repo.get_secrets())
        except GithubException as exc:
            if exc.status in (403, 404):
                continue
            continue

        if not secrets:
            continue

        repos_hit += 1
        total_secrets += len(secrets)
        print(" " * 60, end="\r")

        vis = f"{yellow}private{reset}" if repo.private else f"{green}public{reset}"
        print(f"  {bold}{white}{repo.full_name}{reset}  [{vis}]  {dim}{len(secrets)} secret{'s' if len(secrets) != 1 else ''}{reset}")

        for secret in secrets:
            name       = secret.name
            created_at = getattr(secret, "created_at", None)
            updated_at = getattr(secret, "updated_at", None)

            created_fmt = created_at.strftime("%Y-%m-%d") if created_at else "unknown"
            updated_fmt = updated_at.strftime("%Y-%m-%d") if updated_at else "unknown"

            stale = False
            if updated_at:
                days_since = (now - updated_at.replace(tzinfo=_tz.utc)).days
                stale = days_since > 365
                if stale:
                    stale_count += 1

            stale_tag = f"  {yellow}[not rotated in {days_since}d]{reset}" if stale else ""
            name_col  = yellow if stale else cyan
            print(f"    {name_col}{name}{reset}  {lbl('created:')} {dim}{created_fmt}{reset}  {lbl('updated:')} {dim}{updated_fmt}{reset}{stale_tag}")

        print()

    print(" " * 60, end="\r")

    if repos_hit == 0:
        print(f"  {success('No Actions secrets found in any repository.')}\n")
    else:
        print(f"  {success(f'Found {total_secrets} secret(s) across {repos_hit} of {total} repo(s).')}")
        if stale_count:
            print(f"  {warn(f'{stale_count} secret(s) have not been rotated in over a year.')}")
        print()


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
