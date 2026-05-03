# 09 — Open Questions (v0)

Decisions we have explicitly not made yet. Each one has a default we'll go with if we don't decide before that part is built. Listed in roughly the order they'll need answers.

---

## 1. Is `agent.md` per-KB or one global file?

PRD says: "agent.md can be either per knowledge base or general, TBD."

- **v0 default:** **per-KB.** Each KB folder has its own `agent.md`. Reason: keeps the KB ingestion agent's prompt strictly scoped, and the user can evolve one KB's schema without touching others.
- **Trade-off:** boilerplate duplication. The "always write frontmatter, always update index" rules repeat across files.
- **Mitigation:** factor common rules into the KB ingestion system prompt (`atlasmind/agents/prompts/kb_ingestion_system.md`); per-KB `agent.md` only covers what differs.
- **Revisit when:** we have 6+ KBs and the duplication actually hurts.

## 2. Hobbies KB — include or skip?

PRD flags it as low value. We currently scaffold it but do not load-bear on it.

- **v0 default:** scaffolded, marked `active: false` in `_meta/kb_registry.md` so the router doesn't see it. Easy to flip on.
- **Revisit when:** the user actually has hobby content to file.

## 3. Single-user only — auth strategy

We allowlist Telegram user IDs in `.env` ([`03_telegram_layer.md` §Auth](03_telegram_layer.md)).

- **Open:** what happens if a wrong user persistently hammers the bot? v0 just logs and replies. No rate-limiting beyond Telegram's own.
- **Default:** acceptable. If abused, add a simple counter and silent-mute.

## 4. KB ingestion agent — cache strategy

[§1 of the agent doc](05_agent_layer.md) commits to "cache one agent per KB slug." Open questions:

- **TTL?** Default: never evict. The process is small and 5–6 cached agents is fine.
- **Hot-reload on `agent.md` edit?** v0 default: **no**. The user must restart the process if they edit `agent.md`. (Edit-and-reload is a post-v0 polish item — it requires `agent.md` change detection or per-ingest re-instantiation.)

## 5. Where does the user reply to an HITL question land?

If the user is in the middle of an HITL loop (`expecting="answer"`) and they accidentally send a *new* unrelated message (a voice note about something else), v0 will treat it as the resume answer and confuse the agent.

- **v0 default:** accept this footgun. The agent will likely say "that doesn't look like an answer to my question" and we re-ask. Not great but contained.
- **Revisit:** we could add a magic string ("/cancel") to abandon the HITL session. Probably worth doing during the first build week.

## 6. Routing confidence — is "low" actually used?

The router self-reports confidence. v0 only triggers `ask_user` on `"low"`. Risk: the router never picks `"low"` because it always finds *some* fit, leading to silent misroutes.

- **Default:** start permissive; review after 50 ingests by reading `general_log.md` manually. If confidence is rarely "low" but misroutes happen, tighten the prompt.

## 7. Does the breathing pass run on every ingest or only some?

v0 has the thin breathing pass at the end of every ingestion ([`05_agent_layer.md` §3](05_agent_layer.md)).

- **Default:** every ingest. It's cheap and bounded (single LLM call after note write).
- **Revisit:** if it adds visible latency, gate behind a per-KB flag in `agent.md`.

## 8. Do we sync the Telegram chat_id per-user dynamically?

For unprompted sends (post-v0 recall), we need a `chat_id`. Today we don't store it.

- **v0 default:** record `chat_id` in `_meta/general_log.md` per ingest as soft data. Post-v0 reads it to send recall messages. Avoids a separate user table.

## 9. What actually goes in `_meta/routing_rules.md` on day 1?

Empty file. The user fills it in over time as they notice misroutes.

## 10. Where does the spec live going forward?

This `dev_specs/` directory.

- **Default:** specs are checked into the **code repo** (this one), not the vault. Reason: specs describe how the code works, not the user's data.
- **Edits:** treat spec edits as `docs:` commits in the code repo. The same PR that changes a contract should update the spec doc that defined it.

---

## How to use this doc

If a question above blocks a build task, decide and update both this file and the relevant section in the layer doc. Don't let the default sit silently — every default in here is a decision we're punting, and every punt has interest.
