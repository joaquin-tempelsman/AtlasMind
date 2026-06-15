"""Deployed-version reporting for the /version Telegram command.

The authoritative signal of "what is deployed" is the git HEAD of the running
checkout — the deploy workflow does `git pull origin main`, so the runtime HEAD
equals the deployed commit. An optional `.deploy_stamp` file (written by the
deploy workflow after restart) adds the last deploy/restart time.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

# Repo root = parent of the atlasmind/ package directory.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_STAMP_FILE = ".deploy_stamp"


def _git(args: list[str], repo_root: Path) -> str | None:
    """Run a git command in repo_root, returning trimmed stdout or None on failure."""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def get_version_info(repo_root: Path | None = None) -> dict[str, str | None]:
    """Return the deployed version as a dict.

    Keys: sha, committed_at, subject, deployed. Any value is None when the
    underlying source (git / stamp file) is unavailable.
    """
    root = repo_root or _REPO_ROOT
    sha = _git(["rev-parse", "--short", "HEAD"], root)

    committed_at: str | None = None
    subject: str | None = None
    log = _git(["log", "-1", "--format=%cI%n%s"], root)
    if log:
        lines = log.splitlines()
        committed_at = lines[0] if lines else None
        subject = lines[1] if len(lines) > 1 else None

    stamp_path = root / _STAMP_FILE
    deployed: str | None = None
    if stamp_path.exists():
        deployed = stamp_path.read_text(encoding="utf-8").strip() or None

    return {
        "sha": sha,
        "committed_at": committed_at,
        "subject": subject,
        "deployed": deployed,
    }


def format_version(repo_root: Path | None = None) -> str:
    """Human-readable version string for the Telegram reply."""
    info = get_version_info(repo_root)
    if not info["sha"]:
        return "Version unknown (no git metadata available)."
    lines = [f"AtlasMind @ {info['sha']}"]
    if info["subject"]:
        lines.append(f"• {info['subject']}")
    if info["committed_at"]:
        lines.append(f"• committed {info['committed_at']}")
    if info["deployed"]:
        lines.append(f"• {info['deployed']}")
    return "\n".join(lines)
