# 07 — Git Versioning

## Purpose

Define how AtlasMind uses git for both repos: the **code repo** (engineering) and the **vault repo** (the user's data). They have different lifecycles and different conventions.

---

## 1. Two repos, two strategies

| | Code repo | Vault repo |
|---|---|---|
| Lives at | `~/Documents/AtlasMind/` | `$VAULT_REPO_PATH` (e.g. `~/vault/`) |
| Branches | `main` + feature branches | `main` only in v0 |
| Commits | manual + PR-driven | automated, one per ingest |
| Author | the developer | the AtlasMind process (committer identity below) |
| Pushes | manual / CI | automated after each commit |
| Conflicts | resolved via PR review | surfaced to user via Telegram, resolved manually |

These are kept separate so a bad commit on one never affects the other.

---

## 2. Code repo strategy (this repo)

Standard Python project workflow. Nothing AtlasMind-specific.

### Branch model

- `main` — always green, always deployable.
- Feature branches: `feat/<short-name>`, `fix/<short-name>`, `chore/<short-name>`.
- One PR per feature; squash-merge to main.

### Commit conventions

[Conventional commits](https://www.conventionalcommits.org/) lite. Prefix verbs:
- `feat:` new capability
- `fix:` bug fix
- `refactor:` no behavior change
- `chore:` deps, scripts, build
- `docs:` docs/spec only
- `test:` tests only

Spec edits to `dev_specs/` count as `docs:`.

### What gets committed

- Source code, tests, deploy scripts, this `dev_specs/` directory.
- `requirements.txt`, `pyproject.toml`, `.env.example`, `Makefile`.

### What never gets committed

- `.env` (real secrets)
- `*.ogg`, `*.html` artifacts (those live in the vault repo)
- `.venv/`, `__pycache__/`, `.pytest_cache/`
- Any path inside `$VAULT_REPO_PATH`

`.gitignore` enforces this. v0 inherits a known-good `.gitignore` (the existing one in this repo is fine).

### CI for code repo

Out of scope for v0 spec, but expected:
- Lint + tests on PR
- Deploy on push to `main`

---

## 3. Vault repo strategy (the user's data)

This is the interesting one. The vault is mutated by an automated agent on every ingest, and also by the user (in Obsidian or VSCode). The git layer must keep both happy.

### Branch model

Just `main`. Branches are post-v0 (when we want experiments like "let me try a different schema and revert if it goes badly").

### The ingest commit cycle

For every successful ingest, the pipeline executes (in `vault/git_sync.py`, lifted from talkvault and adapted):

```
1. git pull --ff-only          ← before agent runs (catch user edits)
2. <agent runs, writes files>
3. git add -A
4. git diff --cached --quiet    ← if no changes, skip commit
5. git commit -m "<message>"
6. git push
```

If step 1 fails because the user has un-pushed local edits, we **abort** and reply to the user — we do not stash or auto-merge.

If step 6 fails because the remote moved during the agent run (rare in single-user setup but possible if the user is editing on another device):
- Try once: `git pull --rebase` then `git push`.
- If still rejected: leave the commit local and reply with a "merge needed" message.

### Commit message format

```
<kind>(<kb_slug>): <slug>

routed: <kb_slug> (<confidence>)
note: <relative_path>
pages_touched: <comma_list>
source: <source_kind>
```

`<kind>` is one of `note`, `route` (if router-only), `lint` (post-v0). Example:

```
note(personal-diary): coffee-with-mateo

routed: personal-diary (high)
note: personal-diary/notes/2026-05-02-coffee-with-mateo.md
pages_touched: personal-diary/people/mateo.md, personal-diary/index.md, personal-diary/log.md, _meta/general_log.md
source: voice
```

This shape gives:
- A scannable summary in `git log --oneline`.
- A complete audit trail per commit.
- Easy reverts: a single ingest is one commit.

### Committer identity

Configured in `vault/git_sync.py` at startup, **not** in user-level `~/.gitconfig`:

```
GIT_AUTHOR_NAME=AtlasMind
GIT_AUTHOR_EMAIL=atlasmind@<host>
GIT_COMMITTER_NAME=AtlasMind
GIT_COMMITTER_EMAIL=atlasmind@<host>
```

This makes ingestion commits visually distinct from the user's manual edits in `git log` and in any GitHub UI. The user's manual commits use their normal identity.

### Pull-on-edit (the user's side)

When the user edits a wiki page directly in Obsidian or VSCode:
- They commit and push manually (Obsidian git plugin or `git commit && git push`).
- AtlasMind's next `git pull --ff-only` picks up their changes before the next agent run.

If they don't push before triggering an ingest from another device, conflicts will happen. v0 doesn't solve this — the user is responsible for keeping their devices in sync. Post-v0 fix: a periodic background `git pull` task.

### What about losing data?

The vault is a git repo, with a remote, with one commit per change. The blast radius of any single bug is one ingest. The user can `git revert <commit>` from the command line or from any git UI. We rely on this rather than building app-level undo.

### .gitignore in the vault

Minimal:
```
.obsidian/workspace*
.obsidian/cache*
.DS_Store
.trash/
```

Everything else — including `agent.md`, `_meta/`, `raw/` — is committed. The point of versioning is that the user can see how their schema evolved over time.

---

## 4. Lock contention — concurrent ingests

Single-process, single-tenant v0. Two messages from the same user can arrive within seconds of each other (they often will — voice followed by text correction). The pipeline serializes them with `asyncio.Lock`:

```
async with vault_lock:
    git_pull(...)
    await agent.ainvoke(...)
    git_commit(...)
    git_push(...)
```

While the lock is held, a second incoming message in the edge layer either:
- Routes through HITL because the first is paused on `interrupt()` — the second message is treated as the *answer*, not a new ingest. (Acceptable for v0 — the user knows when the bot is asking.)
- Waits behind the lock if the first is still in agent execution. The edge can send a one-time "queued, working on the previous one..." message if the wait exceeds 2s.

There is no parallelism inside the vault layer. Ever. Concurrent git operations on the same working tree are a corruption hazard.

---

## 5. Why one big commit per ingest (not many small)

An alternative is to commit each file write separately as the agent works. We don't, because:

- An ingest is one logical unit of work. If the agent writes 4 of 7 files and crashes, we want to revert the whole thing, not pick through partial state.
- Git's commit overhead matters at scale. Many small commits balloon the log without adding signal.
- The pipeline's failure mode is "abort and don't commit" — so a partial-write crash leaves the working tree dirty. The next pull sees `git status --porcelain` is non-empty and surfaces the issue. (This is the talkvault `commit_changes` pattern: stage all, check `diff --cached --quiet`, commit only if changes exist.)

Atomic-per-ingest also makes the user's experience clean: `git log` reads as a story of what was added, in order.

---

## 6. Backup posture

v0 expectations from the user:
- The vault repo has a remote. (Private GitHub repo recommended, but any git remote works.)
- After every successful push, the vault is durably backed up.
- The `raw/` folder is part of the repo, so original audio and HTML are backed up too — at the cost of repo size growth. Acceptable in v0; user can `git lfs` it post-v0 if it gets unwieldy.

We do not ship a separate backup mechanism. Git is the backup.
