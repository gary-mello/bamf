# bamf

A Python CLI tool for managing GitHub repositories via Personal Access Token (PAT).

## Features

- **List all repos** — View all accessible repos sorted by most recently updated
- **Clone all repos** — Bulk clone every repo to a local directory
- **Create a repo** — Interactively create a new GitHub repository
- **Search for build files** — Scan repos for build/CI configs across 26 build systems
- **Show PAT info** — Display scopes and metadata for the active token
- **Search for Actions files** — Find GitHub Actions workflow files across repos
- **Repos without branch protection** — Identify repos missing branch protection rules
- **Search for manifest files** — Detect dependency manifests and lockfiles across 40+ ecosystems
- **Scan repos for secrets** — Detect leaked secrets (API keys, tokens, credentials) across all repos using [gitleaks](https://github.com/gitleaks/gitleaks)

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
