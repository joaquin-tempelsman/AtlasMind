#!/usr/bin/env bash
set -euo pipefail

BOOTSTRAP_ONLY=false
if [[ "${1:-}" == "--bootstrap-vault" ]]; then
    BOOTSTRAP_ONLY=true
fi

# ── Python version check ────────────────────────────────────────────────────
if ! python3 --version 2>&1 | grep -qE "Python 3\.1[3-9]"; then
    echo "ERROR: Python 3.13+ is required."
    echo "Install it via pyenv: pyenv install 3.13.2 && pyenv local 3.13.2"
    exit 1
fi

# ── Virtualenv ──────────────────────────────────────────────────────────────
if [[ ! -d ".venv" ]]; then
    echo "Creating .venv..."
    python3 -m venv .venv
fi
PYTHON=".venv/bin/python"
PIP=".venv/bin/pip"

if ! $BOOTSTRAP_ONLY; then
    # ── Install dependencies ────────────────────────────────────────────────
    echo "Installing dependencies..."
    $PIP install -e ".[dev]" --quiet

    # ── Create .env if not present ──────────────────────────────────────────
    if [[ ! -f ".env" ]]; then
        cp .env.example .env
        echo ""
        echo "Created .env from .env.example. Please fill in the required values:"
        echo ""

        read -rp "  TELEGRAM_BOT_TOKEN: " tok
        read -rp "  TELEGRAM_ALLOWED_USER_IDS (comma-separated ints): " ids
        read -rp "  OPENAI_API_KEY: " oai
        read -rp "  VAULT_REPO_PATH (absolute path for the vault repo): " vault

        sed -i.bak \
            -e "s|^TELEGRAM_BOT_TOKEN=.*|TELEGRAM_BOT_TOKEN=${tok}|" \
            -e "s|^TELEGRAM_ALLOWED_USER_IDS=.*|TELEGRAM_ALLOWED_USER_IDS=${ids}|" \
            -e "s|^OPENAI_API_KEY=.*|OPENAI_API_KEY=${oai}|" \
            -e "s|^VAULT_REPO_PATH=.*|VAULT_REPO_PATH=${vault}|" \
            .env
        rm -f .env.bak
        echo ""
    fi
fi

# ── Validate kb_definitions.md ─────────────────────────────────────────────
if [[ ! -f "kb_definitions/kb_definitions.md" ]]; then
    cp kb_definitions/kb_definitions.example.md kb_definitions/kb_definitions.md
    echo ""
    echo "No KB definitions found. A template has been created at:"
    echo "  kb_definitions/kb_definitions.md"
    echo ""
    echo "Edit it to define your knowledge bases, then re-run:"
    echo "  ./setup.sh --bootstrap-vault"
    echo ""
    exit 0
fi

# ── Bootstrap the vault ─────────────────────────────────────────────────────
echo "Bootstrapping vault..."
$PYTHON -m atlasmind.bootstrap

echo ""
echo "Setup complete."
echo "Run:  source .venv/bin/activate && python -m atlasmind.main"
