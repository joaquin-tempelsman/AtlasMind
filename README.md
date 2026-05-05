# AtlasMind

A self-maintained, multi-KB personal knowledge system. Feed it text, voice notes, and links via Telegram — an LLM agent layer classifies each item, files it into the right knowledge base, and commits the result to an Obsidian-compatible vault on git.

## What it does

1. **Receive** — Telegram bot accepts text, voice notes, and URLs.
2. **Normalize** — Voice is transcribed (Whisper); links are fetched and article-extracted; text passes through.
3. **Route** — A router agent picks the correct KB using a stratified sample of recent routing history.
4. **Queue** — Items are held in a per-KB debounce queue (default 5 min). Multiple related items are batched.
5. **Ingest** — A KB-specific agent files notes, updates entity pages, appends to `index.md` and `log.md`, and commits to the vault repo.
6. **Confirm** — The bot replies with a summary. Any clarification needed during routing or ingestion is asked as a Telegram follow-up.

All knowledge bases are generic — defined in `kb_definitions/kb_definitions.md`, never hardcoded. Adding a new KB is one YAML block + `./setup.sh --bootstrap-vault`.

## Tech stack

- Python 3.13, LangChain 1.x + LangGraph, python-telegram-bot 21.x
- OpenAI GPT-4o (routing + ingestion), Whisper (transcription)
- Storage: plain markdown in a git repo (Obsidian-compatible)
- No database, no vector store

## Setup

### Requirements

- Python 3.13 (via pyenv: `pyenv install 3.13.2 && pyenv local 3.13.2`)
- A Telegram bot token (create via [@BotFather](https://t.me/BotFather))
- An OpenAI API key
- A private git repo for your vault (GitHub recommended)

### Install

```bash
git clone https://github.com/<your-fork>/AtlasMind.git
cd AtlasMind
python3 -m venv .venv && source .venv/bin/activate
./setup.sh
```

`setup.sh` will:
1. Install Python dependencies.
2. Prompt for your secrets and write `.env`.
3. Copy `kb_definitions.example.md` if no `kb_definitions.md` exists yet — edit it first, then re-run.
4. Scaffold the vault at `$VAULT_REPO_PATH`.

### Configure your KBs

Edit `kb_definitions/kb_definitions.md`. Each KB block looks like:

```yaml
- name: personal-diary
  description: Daily life, social events, personal observations.
  active: true
  breathing: false
  ingest_delay_min: 5
```

After editing:

```bash
./setup.sh --bootstrap-vault
```

### Run

```bash
python -m atlasmind.main
```

The bot starts polling. Send a message from your allowed Telegram user ID to test it.

## Deployment (Digital Ocean droplet)

1. Provision an Ubuntu droplet and add your SSH key.
2. Clone the repo and run `./setup.sh` on the droplet.
3. Create a systemd service:

```ini
# /etc/systemd/system/atlasmind.service
[Unit]
Description=AtlasMind Telegram bot
After=network.target

[Service]
User=<your-user>
WorkingDirectory=/home/<your-user>/AtlasMind
ExecStart=/home/<your-user>/AtlasMind/.venv/bin/python -m atlasmind.main
Restart=always
RestartSec=5
EnvironmentFile=/home/<your-user>/AtlasMind/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable atlasmind
sudo systemctl start atlasmind
```

4. Add GitHub Actions secrets to your repo:
   - `DROPLET_HOST` — droplet IP or hostname
   - `DROPLET_USER` — SSH user
   - `DROPLET_SSH_KEY` — private key for SSH access

On every push to `main`, CI runs tests then SSHs to the droplet and restarts the service.

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -q

# Lint
ruff check atlasmind/ tests/
```

Tests use `tmp_path` fixtures and mocked LLMs — no real API calls, no `.env` required.

## Project layout

```
atlasmind/
├── config.py              # env loading
├── bootstrap.py           # vault scaffolding from kb_definitions.md
├── pipeline.py            # normalize → route → queue → ingest
├── agents/
│   ├── router.py          # router agent (singleton per vault)
│   ├── kb_ingestion.py    # KB ingestion agent (singleton per vault+KB)
│   ├── prompts/           # system prompt templates
│   └── tools/             # kb_meta, kb_pages, kb_log, interaction
├── edge/
│   ├── session.py         # HITL session table
│   ├── handlers.py        # Telegram message handlers
│   └── telegram_app.py    # Application wiring
├── ingestion/
│   ├── normalize.py       # RawMessage → NormalizedItem
│   ├── transcriber.py     # Whisper
│   └── link_fetcher.py    # readability-lxml
├── shared/
│   └── types.py           # dataclasses: RawMessage, NormalizedItem, RoutedItem
└── vault/
    ├── fs.py              # path-safe read/write
    ├── frontmatter.py     # YAML frontmatter parse/serialize
    ├── paths.py           # slug generation, filename helpers
    └── git_sync.py        # pull/commit/push

kb_definitions/            # your KB definitions (gitignored if private)
dev_specs/                 # architecture + contract docs
dev/                       # feature log, error log
tests/
├── contract/              # cross-layer boundary tests
└── unit/                  # within-layer tests
```

## Architecture docs

See [`dev_specs/`](dev_specs/00_overview.md) for the full spec. Each layer has its own doc. Start with `00_overview.md`.
