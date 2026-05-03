# CLAUDE.md — AtlasMind development guide

This is the guide an agent (or human) follows when working on the AtlasMind code repo. The product spec lives in [`dev_specs/`](dev_specs/00_overview.md). This file governs **how** development happens, not what's being built.

---

## 1. Project orientation

- **What this project is:** see [`dev_specs/00_overview.md`](dev_specs/00_overview.md). One paragraph summary: a Telegram-fed, multi-KB, LLM-maintained Obsidian vault, built in Python 3.13 with LangChain 1.0 agents.
- **Authoritative spec:** anything in `dev_specs/` is the source of truth for contracts. If code disagrees with spec, fix one of them — never silently diverge.
- **Two repos:** this code repo + a separate vault repo at `$VAULT_REPO_PATH`. Never commit vault content here. See [`dev_specs/07_git_versioning.md`](dev_specs/07_git_versioning.md).

---

## 2. The development loop (non-negotiable)

Every feature follows the same five steps, in this order:

1. **Identify the contract.** Find the relevant doc in `dev_specs/`. The contract is a data shape, a tool signature, a file format, or a layer boundary. If no contract exists yet, write the spec section first and commit it as a `docs:` commit before any code.
2. **Write contract tests first.** Tests assert the contract independently of implementation. Cross-layer behavior (e.g. `RawMessage → NormalizedItem`) is tested at the boundary. These tests must fail before any implementation exists.
3. **Implement the feature** in its own branch (`feat/<short-name>`).
4. **Add within-layer tests** alongside the implementation: unit tests for the new functions/classes inside the layer, plus negative paths for anything that can fail.
5. **Open a PR.** PR description references the spec section it implements and the contract tests it satisfies. CI runs all tests; PR does not merge if any contract test or within-layer test fails.

### Hard rules

- **One feature per PR.** If a change touches two unrelated capabilities, split it. A "feature" is the smallest thing that lands a contract.
- **Contracts come first, always.** No "I'll add tests after." If contract tests don't exist, the feature isn't ready to start.
- **Within-layer tests are required.** Contract tests prove the boundary; within-layer tests prove the implementation. Both.
- **Failing tests block merge.** No exceptions, no `--no-verify`, no skipped tests for "I'll fix later."
- **Spec edits are commits.** A change that alters a contract requires a corresponding commit (or PR) to `dev_specs/`.

### What "contract test" means in this project

Concretely:
- For data shapes (`RawMessage`, `NormalizedItem`, etc. — see [`dev_specs/01_architecture.md` §3](dev_specs/01_architecture.md)): tests construct an instance and assert the field set, types, and serialization.
- For tools (router tools, KB ingestion tools — see [`dev_specs/05_agent_layer.md`](dev_specs/05_agent_layer.md)): tests invoke the tool with mocked vault and assert returned shape, side effects on the file system, and path-validation rejections.
- For file formats (frontmatter, `index.md`, `log.md` — see [`dev_specs/06_kb_contract.md`](dev_specs/06_kb_contract.md)): tests round-trip parse → write → parse and assert structural equality.
- For git operations: tests run against a `tmp_path` fixture initialized as a real git repo, asserting commit messages, file lists per commit, and conflict surfacing.

### Test layout

```
tests/
├── contract/             # cross-layer contract tests (run on every PR; gate merge)
│   ├── test_data_shapes.py
│   ├── test_kb_filesystem.py
│   ├── test_router_tools.py
│   └── test_kb_ingestion_tools.py
└── unit/                 # within-layer tests
    ├── test_normalize.py
    ├── test_link_fetcher.py
    ├── test_frontmatter.py
    ├── test_paths.py
    ├── test_git_sync.py
    └── ...
```

CI runs `pytest tests/` — both folders, full suite, every PR.

---

## 3. Branching, commits, PRs

See [`dev_specs/07_git_versioning.md` §2](dev_specs/07_git_versioning.md) for the canonical rules. Highlights:

- Branch off `main`. Names: `feat/<name>`, `fix/<name>`, `refactor/<name>`, `chore/<name>`, `docs/<name>`, `test/<name>`.
- Conventional-commit-lite prefixes on every commit message.
- Squash-merge to `main`.
- PR title = the squash commit subject. PR body must include:
  - Link to the relevant `dev_specs/` section.
  - Bullet list of new/changed contract tests.
  - Bullet list of new/changed within-layer tests.
  - Anything that touches `dev_specs/` is called out.

---

## 4. Tracking discipline (the three logs)

This is the section that makes the project introspectable over time. Three artifacts live in [`dev/`](dev/):

### 4a. `dev/feature_log.md` — long-form feature record

Every merged PR appends one entry. Format:

```markdown
## PR #<num> — <short title>
**Date:** YYYY-MM-DD
**Branch:** feat/<name>
**Layer(s):** <e.g. ingestion, agents.router>
**Spec:** [link to dev_specs section]

### What changed
- 2–5 bullets describing the feature.

### Contracts asserted
- Test file(s) + contract section(s) they cover.

### Within-layer tests added
- File(s) + what they cover.

### Notes
- Anything future-you should remember (gotchas, deferred TODOs, follow-up PRs).
```

Append on merge. Never edit prior entries (errata go in a new entry that says "amends PR #X").

### 4b. `dev/errors.md` — long-form error log

Every non-trivial error encountered during development is filed here. Format:

```markdown
## E-<NNN> — <short title>
**Date:** YYYY-MM-DD
**Encountered in:** <PR # or branch>
**Layer:** <e.g. vault.git_sync>

### What happened
- The actual error: stack trace summary, conditions to reproduce.

### Root cause
- 1–3 sentences. The real reason, not the surface symptom.

### Fix
- What we did. Reference the PR that closed it.

### Learning
- Generalized lesson. What should anyone working on this layer remember?
```

`<NNN>` is a zero-padded counter starting at 001. Errors are immutable once filed — corrections go in a new entry referencing the old one.

What counts as "non-trivial":
- A bug found in code review or tests that wasn't immediately obvious.
- A surprise from an external system (LangChain, Telegram, OpenAI, git).
- A misread of the spec that led to wasted work.
- A flaky test whose flakiness has a real underlying cause.

What does NOT go here:
- Typos or one-line mistakes caught while typing.
- Test failures from incomplete WIP code.

### 4c. The two indexes in this file

Below are kept-current one-line indexes. Update them in the same PR that adds the underlying entry.

---

## 5. Feature index

One line per merged feature, newest at top.

> `<PR#> | YYYY-MM-DD | layer(s) | one-line description`

<!-- BEGIN: feature index -->
<!-- _no entries yet — append on every merge_ -->
<!-- END: feature index -->

---

## 6. Error index

One line per filed error, newest at top.

> `<E-NNN> | YYYY-MM-DD | layer | one-line description (linked to dev/errors.md#e-nnn)`

<!-- BEGIN: error index -->
<!-- _no entries yet — append on every error filed_ -->
<!-- END: error index -->

---

## 7. Workflow recap (the checklist)

For any feature work:

- [ ] Spec section exists in `dev_specs/` (write it first if not).
- [ ] Branch created off `main` with the right prefix.
- [ ] Contract tests written **and failing**.
- [ ] Implementation lands in its own commits.
- [ ] Within-layer unit tests written.
- [ ] All tests pass locally.
- [ ] PR opened referencing spec section + tests.
- [ ] CI green.
- [ ] After merge: append entry to `dev/feature_log.md` + add one-liner to §5 above. Same PR or follow-up `docs:` PR.

For any error encountered during a build:

- [ ] Reproduce it once cleanly.
- [ ] File `E-NNN` entry in `dev/errors.md` with root cause and learning.
- [ ] Add one-liner to §6 above.
- [ ] Reference the error number in the fix PR's commit message.

---

## 8. Tooling expectations

- **Python 3.13.** Match user's pyenv (`.python-version` should pin this once we add it).
- **Dependencies in `requirements.txt`** with explicit minor pins for core libs (`langchain>=1.0`, `python-telegram-bot==21.x`). See [`dev_specs/00_overview.md` §4](dev_specs/00_overview.md).
- **Lint/format:** ruff (default config) — added as a dev dep in the first infra PR.
- **Tests:** `pytest` + `pytest-asyncio`. Markers: `@pytest.mark.contract` for cross-layer tests, `@pytest.mark.unit` for within-layer.
- **Documentation:** when working with libraries (LangChain, python-telegram-bot, OpenAI SDK), use Context7 MCP to fetch current docs rather than relying on training data — see `~/.claude/rules/context7.md`.

---

## 9. Things this guide does not decide

- Deployment topology (covered post-v0 — see [`dev_specs/08_deferred_v0+1.md` §12](dev_specs/08_deferred_v0+1.md)).
- Coverage thresholds (start without one; revisit if tests get sloppy).
- Performance benchmarks (premature for v0).
- Multi-language i18n.

If a workflow question comes up that this file doesn't answer, decide once, write it down here, commit it. The guide is meant to grow.
