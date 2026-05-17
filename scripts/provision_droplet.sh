#!/usr/bin/env bash
# provision_droplet.sh — one-time setup for a fresh Ubuntu droplet
#
# Run as root (or with sudo) on the droplet:
#   bash <(curl -fsSL https://raw.githubusercontent.com/joaquin-tempelsman/AtlasMind/main/scripts/provision_droplet.sh)
# Or after cloning:
#   sudo bash scripts/provision_droplet.sh
#
# What this does:
#   1. Installs system packages needed to build Python
#   2. Installs pyenv + Python 3.13.2
#   3. Clones the AtlasMind repo (or pulls if already present)
#   4. Runs setup.sh (venv, pip install, .env prompts, vault bootstrap)
#   5. Installs and enables the systemd service

set -euo pipefail

REPO_URL="git@github.com:joaquin-tempelsman/AtlasMind.git"
APP_DIR="/root/AtlasMind"
PYTHON_VERSION="3.13.2"
SERVICE_NAME="atlasmind"
SERVICE_USER="root"

# ── colours ──────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[provision]${NC} $*"; }
warn()  { echo -e "${YELLOW}[provision]${NC} $*"; }
die()   { echo -e "${RED}[provision] ERROR:${NC} $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Run as root: sudo bash scripts/provision_droplet.sh"

# ── 1. System packages ────────────────────────────────────────────────────────
info "Installing system packages..."
apt-get update -qq
apt-get install -y --no-install-recommends \
    make build-essential libssl-dev zlib1g-dev \
    libbz2-dev libreadline-dev libsqlite3-dev \
    curl git ca-certificates libffi-dev \
    liblzma-dev libncursesw5-dev tk-dev \
    > /dev/null

# ── 2. pyenv ──────────────────────────────────────────────────────────────────
PYENV_ROOT="/root/.pyenv"

if [[ ! -d "$PYENV_ROOT" ]]; then
    info "Installing pyenv..."
    curl -fsSL https://pyenv.run | bash
fi

# Make pyenv available in this shell session
export PYENV_ROOT
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"

# Persist for future login shells
BASHRC="/root/.bashrc"
if ! grep -q 'pyenv init' "$BASHRC"; then
    cat >> "$BASHRC" <<'EOF'

# pyenv
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"
EOF
fi

# ── 3. Python 3.13 ────────────────────────────────────────────────────────────
if ! pyenv versions --bare | grep -qx "$PYTHON_VERSION"; then
    info "Installing Python $PYTHON_VERSION (this takes a few minutes)..."
    pyenv install "$PYTHON_VERSION"
fi

pyenv global "$PYTHON_VERSION"
info "Python: $(python3 --version)"

# ── 4. SSH key for GitHub (vault + code repo access) ─────────────────────────
SSH_KEY="/root/.ssh/id_ed25519"
if [[ ! -f "$SSH_KEY" ]]; then
    info "Generating SSH key for GitHub access..."
    mkdir -p /root/.ssh
    chmod 700 /root/.ssh
    ssh-keygen -t ed25519 -C "atlasmind-droplet" -f "$SSH_KEY" -N ""
    echo ""
    warn "Add this public key to your GitHub account (Settings → SSH keys):"
    echo "────────────────────────────────────────────────────────────────"
    cat "${SSH_KEY}.pub"
    echo "────────────────────────────────────────────────────────────────"
    echo ""
    read -rp "Press Enter once you've added the key to GitHub... "
    # Verify access
    ssh -T git@github.com -o StrictHostKeyChecking=no 2>&1 | grep -q "successfully authenticated" \
        || warn "GitHub SSH test failed — double-check your key was saved correctly."
fi

# ── 5. Clone or update the repo ───────────────────────────────────────────────
if [[ ! -d "$APP_DIR/.git" ]]; then
    info "Cloning AtlasMind..."
    git clone "$REPO_URL" "$APP_DIR"
else
    info "AtlasMind already cloned — pulling latest..."
    git -C "$APP_DIR" pull origin main
fi

cd "$APP_DIR"

# ── 6. kb_definitions.md (gitignored personal config) ────────────────────────
KB_DEFS="kb_definitions/kb_definitions.md"
if [[ ! -f "$KB_DEFS" ]]; then
    if [[ -f "kb_definitions/kb_definitions.example.md" ]]; then
        cp kb_definitions/kb_definitions.example.md "$KB_DEFS"
    else
        mkdir -p kb_definitions
        cat > "$KB_DEFS" << 'KBEOF'
# KB Definitions — edit this file before running setup.sh --bootstrap-vault
# See kb_definitions/kb_definitions.example.md for the full schema.

```yaml
kbs:
  - slug: personal-diary
    name: Personal Diary
    active: true
    description: |
      Real-world encounters, conversations, events I lived through.
    entities: [people, places]
    breathing: false
    ingest_delay_minutes: 5

  - slug: econ-politics
    name: Economics & Politics
    active: true
    description: |
      News, articles, commentary on economics and politics.
    entities: [people, topics]
    breathing: false
    ingest_delay_minutes: 5
    url_metadata_fields:
      - media_source
      - article_writer
    include_article_content: false
```
KBEOF
    fi
    warn "Created $KB_DEFS — edit it to match your KBs, then re-run:"
    warn "  cd $APP_DIR && ./setup.sh --bootstrap-vault"
    echo ""
    read -rp "Open the file in nano to edit now? [Y/n] " EDIT
    if [[ "${EDIT,,}" != "n" ]]; then
        nano "$KB_DEFS"
    fi
fi

# ── 7. Run setup.sh (venv + deps + .env + vault bootstrap) ───────────────────
info "Running setup.sh..."
bash setup.sh

# ── 8. Systemd service ────────────────────────────────────────────────────────
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

info "Installing systemd service..."
cat > "$SERVICE_FILE" << EOF
[Unit]
Description=AtlasMind Telegram bot
After=network.target

[Service]
User=${SERVICE_USER}
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/.venv/bin/python -m atlasmind.main
Restart=always
RestartSec=5
EnvironmentFile=${APP_DIR}/.env

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl start "$SERVICE_NAME"

sleep 2
if systemctl is-active --quiet "$SERVICE_NAME"; then
    info "Service is running."
else
    warn "Service failed to start. Check logs:"
    warn "  journalctl -u ${SERVICE_NAME} -n 50"
    exit 1
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
info "Provisioning complete."
echo ""
echo "  Status:   sudo systemctl status ${SERVICE_NAME}"
echo "  Logs:     journalctl -u ${SERVICE_NAME} -f"
echo "  Restart:  sudo systemctl restart ${SERVICE_NAME}"
echo ""
echo "Next: add GitHub Actions secrets to enable auto-deploy on push:"
echo "  DROPLET_HOST   — this droplet's IP"
echo "  DROPLET_USER   — ${SERVICE_USER}"
echo "  DROPLET_SSH_KEY — private key whose public key is in ~/.ssh/authorized_keys"
