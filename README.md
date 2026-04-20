# bamf

A Python CLI tool for managing GitHub repositories via Personal Access Token (PAT).

## Features

### RECON

- **List all repos** — View all accessible repos sorted by most recently updated
- **Show PAT info** — Display scopes and metadata for the active token
- **Search for build files** — Scan repos for build/CI configs across 26 build systems
- **Search for Actions files** — Find GitHub Actions workflow files across repos
- **Search for manifest files** — Detect dependency manifests and lockfiles across 40+ ecosystems
- **Repos without branch protection** — Identify repos missing branch protection rules
- **Security posture audit** — Check whether Dependabot alerts, secret scanning, and push protection are enabled on each repo
- **Dependabot vulnerability alerts** — List open CVE alerts by severity (critical/high/medium/low) across all repos
- **Branch protection deep-dive** — Inspect detailed branch protection rules and flag dangerous configs (force push allowed, 0 required reviewers, admins exempt, etc.)
- **Webhook audit** — Enumerate all webhooks and flag insecure ones (HTTP URLs, no SSL verification, missing HMAC secret)
- **Collaborator access audit** — List outside collaborators and pending invitations, flagging admin/write access and stale invites
- **Deploy keys audit** — List all deploy keys, flagging read/write keys and ones that have never been used
- **Actions secrets audit** — Surface GitHub Actions secret names (values are never exposed) and flag secrets not rotated in over a year
- **Scan repos for secrets** — Detect leaked secrets (API keys, tokens, credentials) across all repos using [gitleaks](https://github.com/gitleaks/gitleaks)
- **Workflow injection scan** — Detect `${{ github.event.* }}` expressions flowing into `run:` shell steps (expression injection / RCE); severity escalates to HIGH when paired with dangerous triggers like `pull_request_target` or `issue_comment`
- **Actions permissions audit** — Flag workflows with `permissions: write-all` or no explicit permissions declaration; escalates to CRITICAL when combined with a `pull_request_target` trigger
- **pull_request_target scan** — Identify workflows that use `pull_request_target` + `actions/checkout` with an attacker-controlled `ref:` — a pattern that exposes base-repo secrets to fork PRs (always CRITICAL)
- **Self-hosted runner detection** — Find repos using self-hosted runners via static workflow analysis and live runner API enumeration; online runners highlighted as active attack surface
- **Actions pinning audit** — Flag third-party Actions using mutable tags (`@v3`, `@main`, `@latest`) instead of SHA pins — supply chain risk rated HIGH/MEDIUM/LOW by tag mutability
- **Environment protection audit** — Check deployment environments for missing required-reviewer rules and wait timers; unprotected environments allow unapproved deployments

### PWN

- **Clone all repos** — Bulk clone every repo to a local directory
- **Clone private to public** — Select a private repo, mirror its full history to a new public repo under the same account
- **Create a repo** — Interactively create a new GitHub repository
- **Edit a manifest file** — Select a repo, view a manifest file, edit it in `$EDITOR`, review the diff, and commit changes back to GitHub
- **Nuke branch protections** — Select a repo and branch, then remove all branch protection rules
- **Nuke a repo** — Permanently delete a repository (requires confirmation)
- **Add collaborator** — Select a repo, enter a GitHub username, and add them as a push-level collaborator
- **Inject test workflow** — Create a real GitHub Actions workflow in a target repo for authorized red team testing (payloads: dump runner env, list secret names, or custom command); prompts to clean up the file afterward
- **Fork a repo** — Fork any accessible repository under the authenticated account, with optional custom name and default-branch-only flag

> **Note:** Security audit features (Dependabot alerts, security posture, collaborators, webhooks, deploy keys, Actions secrets) require **admin access** to each repo. Repos where the PAT lacks sufficient permissions are silently skipped.

## Setup

```bash
pip install -r requirements.txt
python main.py
```

### Optional: gitleaks (for secret scanning)

The **Scan repos for secrets** feature requires [gitleaks](https://github.com/gitleaks/gitleaks):

```bash
# macOS
brew install gitleaks

# Linux — download from https://github.com/gitleaks/gitleaks/releases
```

## Authentication

On launch, bamf prompts for a GitHub Personal Access Token (input is hidden). Generate one at:
https://github.com/settings/tokens

- **Classic PAT**: needs `repo` scope for private repo access
- **Fine-Grained PAT**: grant read/write access to specific repos

### Skip the prompt with `--token`

Pass your PAT directly as a flag to bypass the interactive prompt:

```bash
python main.py --token ghp_yourTokenHere
```

This is useful for scripting or CI environments. If the token is invalid, bamf exits immediately with an error.

## Adding a New Menu Option

Import your function from `github_ops.py` and register it in `main.py`:

```python
register_option("Your new feature", lambda: your_function(client))
```

Numbering updates automatically.
