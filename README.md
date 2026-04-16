# bamf

A Python CLI tool for managing GitHub repositories via Personal Access Token (PAT).

## Features

- **List all repos** — View all accessible repos sorted by most recently updated
- **Clone all repos** — Bulk clone every repo to a local directory
- **Create a repo** — Interactively create a new GitHub repository
- **Search for build files** — Scan repos for build/CI configs across 26 build systems

## Setup

```bash
pip install -r requirements.txt
python main.py
```

## Authentication

You will be prompted for a GitHub Personal Access Token on launch. Generate one at:
https://github.com/settings/tokens

- **Classic PAT**: needs `repo` scope for private repo access
- **Fine-Grained PAT**: grant read/write access to specific repos

## Adding a New Menu Option

Import your function from `github_ops.py` and register it in `main.py`:

```python
register_option("Your new feature", lambda: your_function(client))
```

Numbering updates automatically.
