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


def list_repos(client: Github) -> None:
    """List all repos accessible to the authenticated user, sorted by most recently updated."""
    print("\nFetching repositories...\n")

    try:
        user = client.get_user()
        repos = user.get_repos(sort="updated", direction="desc")

        # Column widths
        COL_NUM   = 4
        COL_NAME  = 30
        COL_VIS   = 10
        COL_LANG  = 16
        COL_DESC  = 50

        header = (
            f"{'#':<{COL_NUM}} "
            f"{'Name':<{COL_NAME}} "
            f"{'Visibility':<{COL_VIS}} "
            f"{'Language':<{COL_LANG}} "
            f"{'Description':<{COL_DESC}}"
        )
        divider = "-" * len(header)

        print(header)
        print(divider)

        count = 0
        for repo in repos:
            count += 1
            name = _truncate(repo.name, COL_NAME)
            visibility = "private" if repo.private else "public"
            language = repo.language or "-"
            description = _truncate(repo.description or "", COL_DESC)

            print(
                f"{count:<{COL_NUM}} "
                f"{name:<{COL_NAME}} "
                f"{visibility:<{COL_VIS}} "
                f"{language:<{COL_LANG}} "
                f"{description:<{COL_DESC}}"
            )

        print(divider)
        print(f"\n  Total: {count} repo(s)\n")

    except GithubException as exc:
        if exc.status in (403, 429):
            _handle_rate_limit(client, exc)
        else:
            print(f"\n  GitHub error ({exc.status}): {exc.data.get('message', str(exc))}\n")

    except requests.exceptions.ConnectionError:
        print("\n  Network error: unable to reach GitHub. Check your connection.\n")


def clone_all_repos(client: Github, token: str) -> None:
    """Clone all repos accessible to the authenticated user into a local directory."""
    default_dir = os.path.join(os.getcwd(), "cloned_repos")
    raw = input(f"\nDestination directory [{default_dir}]: ").strip()
    dest = raw if raw else default_dir

    if not shutil.which("git"):
        print("\n  Error: 'git' was not found on your PATH. Please install git and try again.\n")
        return

    try:
        repos = list(client.get_user().get_repos(sort="updated", direction="desc"))
    except GithubException as exc:
        print(f"\n  GitHub error ({exc.status}): {exc.data.get('message', str(exc))}\n")
        return
    except requests.exceptions.ConnectionError:
        print("\n  Network error: unable to reach GitHub. Check your connection.\n")
        return

    if not repos:
        print("\n  No repositories found.\n")
        return

    os.makedirs(dest, exist_ok=True)
    total = len(repos)
    cloned = skipped = failed = 0

    print(f"\nCloning {total} repo(s) into: {dest}\n")

    for i, repo in enumerate(repos, start=1):
        repo_dir = os.path.join(dest, repo.name)
        prefix = f"  ({i}/{total}) {repo.name}"

        if os.path.isdir(repo_dir):
            print(f"{prefix} — skipped (directory already exists)")
            skipped += 1
            continue

        # Embed token in HTTPS URL for authenticated cloning (works for public + private repos)
        owner = repo.owner.login
        clone_url = f"https://x-access-token:{token}@github.com/{owner}/{repo.name}.git"

        result = subprocess.run(
            ["git", "clone", "--quiet", clone_url, repo_dir],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            visibility = "private" if repo.private else "public"
            print(f"{prefix} — cloned  [{visibility}]")
            cloned += 1
        else:
            err = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "unknown error"
            print(f"{prefix} — FAILED: {err}")
            failed += 1

    print(f"\n  Done. Cloned: {cloned}  |  Skipped: {skipped}  |  Failed: {failed}\n")


def create_repo(client: Github) -> None:
    """Interactively create a new GitHub repository."""
    print()

    # --- Name ---
    while True:
        name = input("  Repository name: ").strip()
        if not name:
            print("  Name cannot be empty. Please try again.")
            continue
        if " " in name:
            print("  Name cannot contain spaces (use hyphens or underscores). Please try again.")
            continue
        break

    # --- Visibility ---
    while True:
        vis = input("  Visibility — (p)ublic or (r)ivate? [private]: ").strip().lower()
        if vis in ("", "r", "private"):
            private = True
            break
        if vis in ("p", "public"):
            private = False
            break
        print("  Please enter 'p' for public or 'r' for private.")

    # --- Description (optional) ---
    description = input("  Description (optional, press Enter to skip): ").strip()

    print(f"\n  Creating {'private' if private else 'public'} repo '{name}'...")

    try:
        user = client.get_user()
        repo = user.create_repo(
            name,
            private=private,
            description=description or "",
            auto_init=False,
        )
        print(f"\n  Repository created successfully!")
        print(f"  Name:       {repo.full_name}")
        print(f"  Visibility: {'private' if repo.private else 'public'}")
        print(f"  Clone URL:  {repo.clone_url}")
        print(f"  SSH URL:    {repo.ssh_url}\n")

    except GithubException as exc:
        if exc.status == 422:
            errors = exc.data.get("errors", [])
            msg = errors[0].get("message", "invalid name or repo already exists") if errors else "invalid name or repo already exists"
            print(f"\n  Could not create repo: {msg}\n")
        else:
            print(f"\n  GitHub error ({exc.status}): {exc.data.get('message', str(exc))}\n")

    except requests.exceptions.ConnectionError:
        print("\n  Network error: unable to reach GitHub. Check your connection.\n")


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
        print(f"\n  GitHub error ({exc.status}): {exc.data.get('message', str(exc))}\n")
        return
    except requests.exceptions.ConnectionError:
        print("\n  Network error: unable to reach GitHub. Check your connection.\n")
        return

    if not repos:
        print("\n  No repositories found.\n")
        return

    total = len(repos)
    print(f"\nScanning {total} repo(s) for build files...\n")

    hits = 0

    for i, repo in enumerate(repos, start=1):
        print(f"  Checking ({i}/{total}): {repo.name} ...", end="\r", flush=True)

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
            # Empty repo or permission denied — skip silently
            continue

        root_names = {item.name: item for item in root_contents}

        # --- Match against known build file names ---
        found: list[str] = []
        for filename, label in BUILD_FILES.items():
            if filename in root_names:
                found.append(f"    {filename:<30}  {label}")

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
                    found.append(f"    .github/workflows/{'*':<22}  GitHub Actions  ({actions_count} workflow{'s' if actions_count != 1 else ''})")
            except GithubException:
                pass

        if not found:
            continue

        # --- Print repo header ---
        hits += 1
        print(" " * 60, end="\r")  # clear the progress line

        pushed = repo.pushed_at.strftime("%Y-%m-%d") if repo.pushed_at else "unknown"
        fork_tag = "  [fork]" if repo.fork else ""
        visibility = "private" if repo.private else "public"
        stars = f"★ {repo.stargazers_count}" if repo.stargazers_count else "★ 0"
        open_issues = f"{repo.open_issues_count} open issue{'s' if repo.open_issues_count != 1 else ''}"
        branch = repo.default_branch

        print(f"  {repo.full_name}{fork_tag}")
        print(f"    Visibility:  {visibility}   |   Access: {access}   |   Branch: {branch}")
        print(f"    Language:    {repo.language or '-':<20}  {stars}   |   {open_issues}")
        print(f"    Last push:   {pushed}")
        print(f"    Build files:")
        for line in found:
            print(line)
        print()

    # Clear any leftover progress line
    print(" " * 60, end="\r")

    if hits == 0:
        print("  No build files found in any accessible repository.\n")
    else:
        print(f"  Found build files in {hits} of {total} repo(s).\n")


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

        divider = "-" * 60
        print(divider)
        print("  Token Details")
        print(divider)
        print(f"  Type:          {token_type}")
        print(f"  Prefix:        {token[:8]}{'*' * 10}  (first 8 chars shown)")
        print()

        print(divider)
        print("  Account")
        print(divider)
        print(f"  Login:         {user.login}")
        if user.name:
            print(f"  Name:          {user.name}")
        if user.email:
            print(f"  Email:         {user.email}")
        print(f"  Account type:  {'Organization' if user.type == 'Organization' else 'Personal'}")
        if user.company:
            print(f"  Company:       {user.company}")
        if user.plan:
            print(f"  GitHub plan:   {user.plan.name}")
        print(f"  Public repos:  {user.public_repos}")
        print(f"  Private repos: {user.total_private_repos or 0}")
        print(f"  Followers:     {user.followers}  |  Following: {user.following}")
        print()

        print(divider)
        if token_type == "Fine-Grained PAT":
            print("  Permissions  (fine-grained — per-repository)")
            print(divider)
            print("  Fine-grained PATs use per-repository permissions rather than")
            print("  global scopes. Permissions are not enumerable via the REST API.")
            print("  Manage this token at: https://github.com/settings/tokens")
        else:
            print(f"  Scopes  ({len(scopes)} granted)")
            print(divider)
            if scopes:
                for scope in scopes:
                    desc = SCOPE_DESCRIPTIONS.get(scope, "")
                    bullet = f"  • {scope:<28}"
                    print(f"{bullet}  {desc}" if desc else bullet)
            else:
                print("  (none) — token has read-only access to public data only")
        print()

        print(divider)
        print("  Rate Limits")
        print(divider)

        from datetime import datetime, timezone as tz

        def _fmt_resource(res: dict) -> str:
            remaining = res.get("remaining", "?")
            limit = res.get("limit", "?")
            reset_ts = res.get("reset")
            reset_str = (
                datetime.fromtimestamp(reset_ts, tz=tz.utc).strftime("%H:%M UTC")
                if reset_ts else "unknown"
            )
            return f"{remaining:>6,} / {limit:,} remaining  (resets {reset_str})" if isinstance(remaining, int) else f"{remaining} / {limit}"

        for label, key in [("Core API", "core"), ("Search API", "search"), ("GraphQL API", "graphql")]:
            res = rate_resources.get(key)
            if res is not None:
                print(f"  {label:<14} {_fmt_resource(res)}")
        print()

    except GithubException as exc:
        if exc.status in (403, 429):
            _handle_rate_limit(client, exc)
        else:
            print(f"\n  GitHub error ({exc.status}): {exc.data.get('message', str(exc))}\n")
    except requests.exceptions.ConnectionError:
        print("\n  Network error: unable to reach GitHub. Check your connection.\n")


def search_actions_files(client: Github) -> None:
    """Scan all accessible repos for GitHub Actions workflow files and list them."""
    try:
        repos = list(client.get_user().get_repos(sort="updated", direction="desc"))
    except GithubException as exc:
        print(f"\n  GitHub error ({exc.status}): {exc.data.get('message', str(exc))}\n")
        return
    except requests.exceptions.ConnectionError:
        print("\n  Network error: unable to reach GitHub. Check your connection.\n")
        return

    if not repos:
        print("\n  No repositories found.\n")
        return

    total = len(repos)
    print(f"\nScanning {total} repo(s) for GitHub Actions workflow files...\n")

    total_workflows = 0
    repos_with_actions = 0

    for i, repo in enumerate(repos, start=1):
        print(f"  Checking ({i}/{total}): {repo.name} ...", end="\r", flush=True)

        try:
            contents = repo.get_contents(".github/workflows")
        except GithubException:
            # Folder missing or permission denied — skip
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

        print(" " * 60, end="\r")  # clear progress line

        visibility = "private" if repo.private else "public"
        pushed = repo.pushed_at.strftime("%Y-%m-%d") if repo.pushed_at else "unknown"
        wf_count = len(yml_files)
        print(f"  {repo.full_name}  [{visibility}]  —  last push: {pushed}  —  {wf_count} workflow{'s' if wf_count != 1 else ''}")

        for wf in yml_files:
            print(f"    • {wf.name:<40}  {wf.path}")

        print()

    print(" " * 60, end="\r")

    if repos_with_actions == 0:
        print("  No GitHub Actions workflow files found in any accessible repository.\n")
    else:
        print(
            f"  Found {total_workflows} workflow file{'s' if total_workflows != 1 else ''} "
            f"across {repos_with_actions} of {total} repo(s).\n"
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
            f"\n  Rate limit exceeded. Limit resets at {reset_utc.strftime('%H:%M:%S UTC')}. "
            f"({rate.remaining} requests remaining)\n"
        )
    except Exception:
        print(f"\n  GitHub error ({exc.status}): {exc.data.get('message', str(exc))}\n")
