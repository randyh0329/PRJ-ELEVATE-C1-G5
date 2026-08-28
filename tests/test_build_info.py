"""Reporting which commit is running, in `/health` and in the served page.

The value of this is entirely in it being *right*. A version badge that is
merely plausible is worse than none: it is the thing a developer will act on
when deciding whether their fix is deployed, and a stale or invented SHA sends
them looking for a bug that is already fixed, or shipping a fix twice.

So the tests below are mostly about the three ways it can be wrong. The
environment variable must win, because in the container it is the only source
that exists. Git must be consulted only when it does not. And a failure of
either - no git binary, no repository, a non-zero exit - has to surface as
`unknown` rather than as a guess or a stack trace on the landing page.
"""

from __future__ import annotations

import subprocess

import pytest
from fastapi.testclient import TestClient

from src.main import _build_badge_html, app
from src.telemetry.build_info import (
    DEFAULT_COMMIT_URL_BASE,
    UNKNOWN,
    BuildInfo,
    get_build_info,
)

SHA = "1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d"


@pytest.fixture(autouse=True)
def uncached():
    """`get_build_info` memoises for the process; every test needs a fresh look."""
    get_build_info.cache_clear()
    yield
    get_build_info.cache_clear()


@pytest.fixture
def no_git(monkeypatch):
    """Make every git call fail, the way it does inside the container."""
    monkeypatch.setattr(
        "src.telemetry.build_info._git", lambda *args: None
    )


# --- resolution order ---------------------------------------------------------


def test_the_environment_variable_is_the_first_source(monkeypatch):
    """It is the only one that works in the image - nothing copies `.git`."""
    monkeypatch.setenv("GIT_COMMIT_SHA", SHA)

    build = get_build_info()

    assert build.commit == SHA
    assert build.short == "1a2b3c4"


def test_a_baked_in_commit_is_never_reported_dirty(monkeypatch):
    """The tree it was built from is long gone and unknowable from in here.

    Without this the container would shell out to git, find no repository, and
    the answer would depend on whatever the build daemon happened to leave in
    the working directory.
    """
    monkeypatch.setenv("GIT_COMMIT_SHA", SHA)
    monkeypatch.setattr(
        "src.telemetry.build_info._git",
        lambda *args: pytest.fail("git must not be consulted when the SHA is baked in"),
    )

    assert get_build_info().dirty is False


def test_a_blank_environment_variable_falls_through_to_git(monkeypatch):
    """An unset build arg reaches the container as "", not as absent."""
    monkeypatch.setenv("GIT_COMMIT_SHA", "   ")
    monkeypatch.setattr(
        "src.telemetry.build_info._git",
        lambda *args: SHA if args[0] == "rev-parse" else "",
    )

    assert get_build_info().commit == SHA


def test_git_supplies_the_commit_for_a_local_run(monkeypatch):
    monkeypatch.delenv("GIT_COMMIT_SHA", raising=False)
    monkeypatch.setattr(
        "src.telemetry.build_info._git",
        lambda *args: SHA if args[0] == "rev-parse" else "",
    )

    build = get_build_info()

    assert build.commit == SHA
    assert build.dirty is False


def test_a_modified_tracked_file_makes_the_build_dirty(monkeypatch):
    monkeypatch.delenv("GIT_COMMIT_SHA", raising=False)
    monkeypatch.setattr(
        "src.telemetry.build_info._git",
        lambda *args: SHA if args[0] == "rev-parse" else " M src/main.py",
    )

    build = get_build_info()

    assert build.dirty is True
    assert build.label == "1a2b3c4-dirty"


def test_untracked_files_alone_do_not_count_as_dirty(monkeypatch):
    """`var/`, built indexes and scratch notes do not change what is running."""
    seen = []

    def _git(*args):
        seen.append(args)
        return SHA if args[0] == "rev-parse" else ""

    monkeypatch.delenv("GIT_COMMIT_SHA", raising=False)
    monkeypatch.setattr("src.telemetry.build_info._git", _git)

    assert get_build_info().dirty is False
    assert ("status", "--porcelain", "--untracked-files=no") in seen


def test_no_git_and_no_variable_is_reported_as_unknown(monkeypatch, no_git):
    """Said plainly. A wrong SHA is worse than none - it is the one acted on."""
    monkeypatch.delenv("GIT_COMMIT_SHA", raising=False)

    build = get_build_info()

    assert build.commit == UNKNOWN
    assert build.short == UNKNOWN
    assert build.label == UNKNOWN
    assert build.url is None


# --- the git shell-out --------------------------------------------------------


def test_a_missing_git_binary_is_not_an_exception(monkeypatch):
    """This runs during a page render; it may not take the landing page down."""
    def _explode(*args, **kwargs):
        raise FileNotFoundError("No such file or directory: 'git'")

    monkeypatch.setattr(subprocess, "run", _explode)
    monkeypatch.delenv("GIT_COMMIT_SHA", raising=False)

    assert get_build_info().commit == UNKNOWN


def test_a_git_call_that_hangs_is_abandoned(monkeypatch):
    def _hang(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="git", timeout=2.0)

    monkeypatch.setattr(subprocess, "run", _hang)
    monkeypatch.delenv("GIT_COMMIT_SHA", raising=False)

    assert get_build_info().commit == UNKNOWN


def test_a_directory_that_is_not_a_repository_yields_unknown(monkeypatch):
    """`git rev-parse` exits 128 here; a non-zero exit is not an answer."""
    def _fail(*args, **kwargs):
        return subprocess.CompletedProcess(args=[], returncode=128, stdout="", stderr="not a git repository")

    monkeypatch.setattr(subprocess, "run", _fail)
    monkeypatch.delenv("GIT_COMMIT_SHA", raising=False)

    assert get_build_info().commit == UNKNOWN


def test_the_answer_is_resolved_once_per_process(monkeypatch):
    """The fallback shells out twice; the served page must not pay that per hit."""
    calls = []
    monkeypatch.delenv("GIT_COMMIT_SHA", raising=False)
    monkeypatch.setattr(
        "src.telemetry.build_info._git",
        lambda *args: (calls.append(args), SHA if args[0] == "rev-parse" else "")[1],
    )

    for _ in range(5):
        get_build_info()

    assert len(calls) == 2


# --- the commit link ----------------------------------------------------------


def test_the_commit_links_to_the_repository():
    assert BuildInfo(SHA, SHA[:7], dirty=False).url == DEFAULT_COMMIT_URL_BASE + SHA


def test_a_dirty_tree_still_links_to_its_commit():
    """HEAD is where the reader should start; `label` already warned them."""
    assert BuildInfo(SHA, SHA[:7], dirty=True).url.endswith(SHA)


def test_the_link_base_can_be_repointed_at_a_fork(monkeypatch):
    monkeypatch.setenv("GIT_COMMIT_URL_BASE", "https://ghe.corp/hr/agentic/commit")

    assert BuildInfo(SHA, SHA[:7], dirty=False).url == f"https://ghe.corp/hr/agentic/commit/{SHA}"


# --- what /health reports -----------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_the_health_probe_reports_the_running_commit(client, monkeypatch):
    monkeypatch.setenv("GIT_COMMIT_SHA", SHA)

    body = client.get("/health").json()

    assert body["build"] == {"commit": SHA, "short": "1a2b3c4", "dirty": False, "label": "1a2b3c4"}


def test_the_health_probe_keeps_its_existing_contract(client):
    """Uptime checks read `status`; adding a field must not move the old ones."""
    body = client.get("/health").json()

    assert body["status"] == "HEALTHY"
    assert body["service"] == "hr-agentic-solution"
    assert body["version"] == "0.1.0"


# --- what the page shows ------------------------------------------------------


def test_the_page_header_carries_the_short_commit(client, monkeypatch):
    monkeypatch.setenv("GIT_COMMIT_SHA", SHA)

    page = client.get("/").text

    assert "1a2b3c4" in page
    assert f"{DEFAULT_COMMIT_URL_BASE}{SHA}" in page
    assert "__BUILD_BADGE__" not in page


def test_the_full_sha_is_the_hover_text():
    """Seven characters identify the commit; forty are what you paste into git."""
    badge = _build_badge_html(BuildInfo(SHA, SHA[:7], dirty=False))

    assert f'title="{SHA}"' in badge


def test_a_dirty_build_says_so_on_the_badge():
    badge = _build_badge_html(BuildInfo(SHA, SHA[:7], dirty=True))

    assert "1a2b3c4-dirty" in badge
    assert "build-badge-dirty" in badge
    assert "running local edits" in badge


def test_an_unknown_build_is_not_rendered_as_a_link():
    """An `<a>` with an empty href reloads the page - a worse lie than saying so."""
    badge = _build_badge_html(BuildInfo(UNKNOWN, UNKNOWN, dirty=False))

    assert badge.startswith("<span")
    assert "href" not in badge
    assert "unknown" in badge


def test_a_hostile_commit_value_cannot_break_out_of_the_badge():
    """The SHA arrives from an environment variable, so it is not trusted input."""
    injected = '"><script>alert(1)</script>'

    badge = _build_badge_html(BuildInfo(injected, injected, dirty=False))

    assert "<script>" not in badge
    assert "&lt;script&gt;" in badge
