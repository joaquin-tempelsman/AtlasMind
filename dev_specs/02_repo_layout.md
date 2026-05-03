# 02 — Repo Layout

There are **two repos** in AtlasMind, and keeping them separate is deliberate.

1. **The code repo** — `atlasmind/` — Python source, tests, deploy scripts, KB definitions. This is the project repo.
2. **The vault repo** — a separate git repo whose path is configured via `VAULT_REPO_PATH`. The user opens this in Obsidian. The code reads/writes it at runtime.

This mirrors talkvault: code lives in one repo, the user's data lives in another. It also means the user can publish, back up, and version their knowledge independently of the code that builds it.

---

## 1. Code repo layout

```
atlasmind/
├── atlasmind/
│   ├── __init__.py
│   ├── main.py                      # entry point: starts Telegram app
│   ├── bootstrap.py                 # one-shot vault scaffolding from kb_definitions.md
│   ├── config.py                    # env var loading, single source of truth
│   │
│   ├── shared/
│   │   ├── __init__.py
│   │   ├── types.py                 # RawMessage, NormalizedItem, RoutedItem, IngestionResult
│   │   ├── kb_registry.py           # loads KB metadata from kb_definitions.md on startup
│   │   └── logging.py               # structured logging setup
│   │
│   ├── edge/
│   │   ├── __init__.py
│   │   ├── telegram_app.py          # Application + handler wiring
│   │   ├── handlers.py              # handle_voice, handle_text — thin adapters
│   │   └── session.py               # session table for HITL interrupts
│   │
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── normalize.py             # RawMessage → NormalizedItem
│   │   ├── transcriber.py           # voice → text (Whisper)
│   │   └── link_fetcher.py          # url → text + title (v0: readability-lxml)
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── router.py                # builds the routing agent
│   │   ├── kb_ingestion.py          # builds a KB-scoped ingestion agent; per-KB cache
│   │   ├── prompts/
│   │   │   ├── router_system.md     # routing system prompt template
│   │   │   └── kb_ingestion_system.md  # ingestion system prompt template (per-KB substitutions)
│   │   └── tools/
│   │       ├── __init__.py
│   │       ├── interaction.py       # ask_user (LangGraph interrupt)
│   │       ├── kb_meta.py           # list_kbs, read_recent_routing (stratified), commit_route
│   │       ├── kb_pages.py          # read_page, write_page, list_pages, search_pages (within one KB)
│   │       └── kb_log.py            # append_kb_log
│   │
│   ├── vault/
│   │   ├── __init__.py
│   │   ├── fs.py                    # safe markdown read/write under VAULT_REPO_PATH
│   │   ├── frontmatter.py           # YAML frontmatter parse/serialize
│   │   ├── paths.py                 # path conventions (slugs, dates, KB folders)
│   │   └── git_sync.py              # pull, commit, push (lifted from talkvault)
│   │
│   └── pipeline.py                  # orchestrates L1→L4; per-KB ingest queue + debounce timers
│
├── kb_definitions/
│   ├── kb_definitions.example.md   # generic template — copy and fill in to define your KBs
│   └── kb_definitions.md           # your actual KB definitions (gitignore-able for private instances)
│
├── tests/
│   ├── conftest.py
│   ├── test_normalize.py
│   ├── test_router.py               # mocked LLM, real prompt assembly
│   ├── test_kb_ingestion.py         # mocked LLM, fake vault on tmp_path
│   ├── test_vault_fs.py
│   ├── test_frontmatter.py
│   └── test_git_sync.py
│
├── dev_specs/                       # this directory
├── base_docs/                       # PRD + llm_wiki idea
│
├── .github/
│   └── workflows/
│       └── deploy.yml               # push-to-main → test → deploy to Digital Ocean droplet
│
├── setup.sh                         # fresh-clone onboarding: deps, .env, KB scaffold
├── pyproject.toml
├── requirements.txt
├── .env.example
├── .gitignore
├── CLAUDE.md                        # agent-facing project guide (lives in code repo)
└── README.md
```

**Module ownership rules:**

- `edge.*` is the only thing that touches `python-telegram-bot`.
- `vault.*` is the only thing that touches the filesystem under `VAULT_REPO_PATH` and the only thing that runs `git`.
- `agents.tools.*` are the bridge: they call `vault.*` to do real work.
- `pipeline.py` is the only place L1, L2, L3, L4 are wired together and where the per-KB ingest queue lives.
- `kb_definitions/kb_definitions.md` is the single source of truth for which KBs exist. `bootstrap.py` reads it; nothing else defines KBs.

---

## 2. Vault repo layout (the user's data repo)

This is what `VAULT_REPO_PATH` points to. The user opens it in Obsidian to read.

```
my-atlasmind-vault/
├── _meta/
│   ├── kb_registry.md               # GENERATED from kb_definitions.md by bootstrap — do not edit
│   ├── general_log.md               # ALL routing decisions (chronological, append-only)
│   └── routing_rules.md             # human-editable hints the router reads
│
├── <kb-slug>/                       # one folder per KB defined in kb_definitions.md
│   ├── agent.md                     # KB-specific schema/prompt addendum (user-editable)
│   ├── index.md                     # catalog of pages in this KB
│   ├── log.md                       # chronological per-KB log
│   ├── notes/
│   │   └── YYYY-MM-DD-<slug>.md
│   └── <entity-folder>/             # created on demand per agent.md (people/, topics/, books/, etc.)
│       └── <slug>.md
│
├── raw/                             # immutable original sources (scraped html for links)
│   └── links/
│       └── 2026-05-02T14-25-03Z__<sha1>.html
│
└── .obsidian/                       # user-owned; we never write here
```

The vault structure is KB-agnostic. Bootstrap creates one `<kb-slug>/` folder per entry in `kb_definitions.md`. There is no hardcoded KB structure in the code.

**Conventions enforced by `vault.paths`:**

- KB folders are slug-form (`personal-diary`, not `Personal Diary`). The display name lives in `_meta/kb_registry.md`.
- Every KB has the same four scaffolded files: `agent.md`, `index.md`, `log.md`, plus its `notes/` folder. Entity folders are created on demand.
- Notes are named `YYYY-MM-DD-<slug>.md`. Date is the **received_at** date in the user's local TZ at write time. Kebab-case slug ≤ 6 words.
- The agent never writes outside its assigned KB folder *except* via the `commit_route` tool (router only) which appends to `_meta/general_log.md`. The KB ingestion agent has no access to `_meta/`.
- `raw/` is append-only for link HTML. Raw audio is not persisted (see [`04_ingestion_layer.md`](04_ingestion_layer.md)).

---

## 3. Why this split (code vs vault)

- **Privacy:** the user can keep the vault private even if the code repo goes public.
- **Backup independence:** the vault gets its own remote (e.g. a private GitHub repo or a self-hosted git server).
- **Multiple users / multiple vaults:** the same code can serve a second vault without code changes — just a different `VAULT_REPO_PATH`. Not a v0 feature, but the boundary makes it free later.
- **The vault is the product.** The code is a means to maintain the vault. The user's git history of the vault is the artifact they care about; the code's git history is engineering churn.

---

## 4. `setup.sh` — fresh-clone onboarding

Running `setup.sh` after cloning is the complete onboarding path. No other setup steps required.

```
git clone <repo>
cd atlasmind
./setup.sh
```

The script does:
1. **Check Python 3.13+.** Exits with instructions if not found.
2. **Install dependencies.** `pip install -e .`
3. **Create `.env` from `.env.example`** if it doesn't exist, then interactively prompt for each required variable:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_ALLOWED_USER_IDS` (comma-separated)
   - `OPENAI_API_KEY`
   - `VAULT_REPO_PATH` (absolute path to where the vault should live)
4. **Validate `kb_definitions/kb_definitions.md`.** If it doesn't exist, copy `kb_definitions.example.md` → `kb_definitions.md` and print: `"No KB definitions found. A template has been created at kb_definitions/kb_definitions.md. Edit it to define your knowledge bases, then re-run setup.sh --bootstrap-vault."` Exit.
5. **Bootstrap the vault.** `python -m atlasmind.bootstrap` — reads `kb_definitions.md`, `git init`s the vault at `VAULT_REPO_PATH` if needed, scaffolds all KB folders, generates `_meta/kb_registry.md`, makes the initial commit.
6. **Print confirmation.** `"Setup complete. Run: python -m atlasmind.main"`

`--bootstrap-vault` flag reruns only step 5 (useful when adding a new KB to `kb_definitions.md` without redoing all other setup).

---

## 5. CI/CD — `.github/workflows/deploy.yml`

Trigger: push to `main`.

```yaml
name: Deploy to Digital Ocean

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: pip install -e ".[dev]"
      - run: pytest

  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to droplet
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.DO_HOST }}
          username: ${{ secrets.DO_USER }}
          key: ${{ secrets.DO_SSH_KEY }}
          script: |
            cd ~/atlasmind
            git pull origin main
            pip install -e .
            systemctl restart atlasmind
```

**Required GitHub secrets:** `DO_HOST`, `DO_USER`, `DO_SSH_KEY`.

**Droplet setup requirements:**
- Python 3.13 installed
- `atlasmind` running as a `systemd` service (`/etc/systemd/system/atlasmind.service`)
- The vault repo at `VAULT_REPO_PATH` on the droplet (separate from the code repo; has its own remote)
- `.env` already present on the droplet (not in the repo; set up once manually via SSH)
- `kb_definitions/kb_definitions.md` present on the droplet (same manual step)

**What the CI/CD does NOT do:**
- Touch the vault repo (that's live data; the droplet manages it independently)
- Update `.env` or `kb_definitions.md` (those are manual operations)
- Roll back on failure (post-v0; for now the prior version is gone until a revert commit is pushed)
