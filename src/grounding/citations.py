"""Repo-relative paths to citation URLs a human can actually open.

Every citation this system emits points at a file in this repository - an OKF
concept under `okf/`, or the raw handbook at the root. Until now those were
rendered either as bare paths (`leave/bereavement.md#allowance`, which is not a
link) or as invented hostnames (`https://hr.corp.internal/policies/...`, which
is worse: it renders as a link, resolves to nothing, and cannot be told apart
from a working one by reading the answer).

FR-5.3 says a citation that does not resolve is not a citation. A URL that
*looks* resolvable and is not fails that requirement in the one way review
cannot catch, so the base is configurable and defaults to the repository's own
GitHub blob view - somewhere the cited text is genuinely visible.

Set `POLICY_RAG_CITATION_BASE_URL` to repoint this: a fork, a pinned commit
instead of `main`, or an internal mirror once one exists.
"""

from __future__ import annotations

import os
from urllib.parse import quote

#: Blob view of this repository at `main`. `main` rather than a commit SHA
#: because a citation should show the policy as it stands, and the corpus is
#: versioned by the handbook's own `stale_after` dates rather than by git.
DEFAULT_CITATION_BASE_URL = "https://github.com/randyh0329/PRJ-ELEVATE-C1-G5/blob/main/"

ENV_VAR = "POLICY_RAG_CITATION_BASE_URL"


def citation_base_url() -> str:
    """The configured base, always with exactly one trailing slash.

    Read per call rather than cached at import: tests and the ingest CLI both
    set this in the environment, and a module-level constant captured at import
    time would silently ignore them.
    """
    base = os.environ.get(ENV_VAR, "").strip() or DEFAULT_CITATION_BASE_URL
    return base.rstrip("/") + "/"


def blob_url(repo_path: str, anchor: str | None = None) -> str:
    """URL for a repo-relative path, e.g. `okf/.../bereavement.md#allowance`.

    Path segments are percent-encoded individually so that `/` survives and
    everything else does not. This matters more than it looks: the handbook is
    checked in as `ALTOSTRAT SINGAPORE EMPLOYEE POLICY HANDBOOK & CONDUCT
    GUIDELINES.md`, and an unencoded space or `&` truncates the link at the
    first offending character - producing, again, a URL that renders fine and
    goes nowhere.

    The anchor is passed through unencoded. Anchors here come from `slugify`,
    which already emits only `[a-z0-9-]`, and percent-encoding a `#` fragment
    is what breaks GitHub's own heading links.
    """
    path = "/".join(quote(segment) for segment in repo_path.strip("/").split("/"))
    url = f"{citation_base_url()}{path}"
    return f"{url}#{anchor}" if anchor else url
