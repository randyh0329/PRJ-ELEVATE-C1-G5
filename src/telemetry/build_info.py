"""Which commit is running, so a developer looking at the UI can tell.

The question this answers is the one asked in front of a deployed service:
*is my fix in this?* Answering it from the outside currently means correlating
a Cloud Run revision name against a GitHub Actions run, and the two agree only
if nobody has deployed by hand since.

Three sources, consulted in order, because no single one works everywhere:

1. ``GIT_COMMIT_SHA`` from the environment. The only one that works in the
   container: the Dockerfile copies ``config/``, ``src/`` and ``pyproject.toml``
   and nothing else, so there is no ``.git`` to interrogate at runtime. CI bakes
   the value in with ``--build-arg``, which makes the image self-describing -
   ``docker run`` it anywhere and it still knows what it is.
2. ``git rev-parse`` against the working tree, for a local run. This source can
   also report a dirty tree, which is the sharper form of the question when you
   are running locally: am I looking at HEAD, or at my uncommitted edits?
3. ``"unknown"`` - a source checkout with neither git nor the variable set. Said
   plainly rather than guessed at, because a wrong commit is worse than no
   commit: it is the answer you would act on.

Only the *tracked* tree counts towards dirtiness. Untracked files are usually
scratch output (``var/``, ``.faiss`` indexes, notes) and do not change which
version is running.
"""

from __future__ import annotations

import functools
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("telemetry.build_info")

ENV_VAR = "GIT_COMMIT_SHA"

#: Where to point a reader at a commit. Env-overridable for a fork or a mirror.
#: Deliberately not derived from `src/grounding/citations.py`: that base is a
#: *blob* view pinned to `main` and may be repointed at an internal mirror with
#: no `/commit/` route at all. Same host today, different things.
DEFAULT_COMMIT_URL_BASE = "https://github.com/randyh0329/PRJ-ELEVATE-C1-G5/commit/"
COMMIT_URL_ENV_VAR = "GIT_COMMIT_URL_BASE"

UNKNOWN = "unknown"

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GIT_TIMEOUT_SECONDS = 2.0


@dataclass(frozen=True)
class BuildInfo:
    """The running version, in the several forms the callers want it."""

    commit: str
    """Full 40-character SHA, or ``"unknown"``."""

    short: str
    """First seven characters, or ``"unknown"``."""

    dirty: bool
    """Tracked files differ from HEAD. Only ever true for a local run."""

    @property
    def label(self) -> str:
        """What to show a human: ``1a2b3c4``, ``1a2b3c4-dirty``, ``unknown``."""
        return f"{self.short}-dirty" if self.dirty else self.short

    @property
    def url(self) -> str | None:
        """Link to the commit, or ``None`` when there is nothing to link to.

        A dirty tree still links to HEAD: the commit is where the reader should
        start, and `label` has already warned them the tree has moved on.
        """
        if self.commit == UNKNOWN:
            return None
        base = os.environ.get(COMMIT_URL_ENV_VAR, "").strip() or DEFAULT_COMMIT_URL_BASE
        return base.rstrip("/") + "/" + self.commit

    def as_dict(self) -> dict[str, object]:
        """The shape `/health` reports."""
        return {"commit": self.commit, "short": self.short, "dirty": self.dirty, "label": self.label}


def _git(*args: str) -> str | None:
    """Run a git command in the repo, or return None if git cannot answer."""
    try:
        # Fixed argv, no shell, no interpolation of anything a caller supplies.
        result = subprocess.run(
            ["git", *args],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        # No git binary, no repository, or it hung. All mean the same thing here.
        logger.debug("git %s unavailable: %s", " ".join(args), exc)
        return None
    if result.returncode != 0:
        logger.debug("git %s failed: %s", " ".join(args), result.stderr.strip())
        return None
    return result.stdout.strip()


def _resolve() -> BuildInfo:
    env_sha = os.environ.get(ENV_VAR, "").strip()
    if env_sha:
        # Baked at build time, so the tree it came from is irrelevant and
        # unknowable. Never dirty.
        return BuildInfo(commit=env_sha, short=env_sha[:7], dirty=False)

    commit = _git("rev-parse", "HEAD")
    if not commit:
        return BuildInfo(commit=UNKNOWN, short=UNKNOWN, dirty=False)

    # `--untracked-files=no`: see the module docstring. Also the faster mode.
    status = _git("status", "--porcelain", "--untracked-files=no")
    return BuildInfo(commit=commit, short=commit[:7], dirty=bool(status))


@functools.lru_cache(maxsize=1)
def get_build_info() -> BuildInfo:
    """The running version, resolved once per process.

    Cached because it cannot change while the process lives, and because the
    fallback path shells out to git - once at startup is fine, once per request
    on the served page is not. `get_build_info.cache_clear()` in tests.
    """
    return _resolve()
