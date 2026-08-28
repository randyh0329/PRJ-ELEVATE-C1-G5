"""What the container images are required to contain.

`tests/test_api_server.py` already asserts that a running instance can answer a
policy question. It cannot catch the failure this file exists for: those tests
execute against the repo checkout, where `okf/` is always on disk, so they pass
green no matter what the Dockerfile copies. The image is the thing that was
wrong, and nothing was reading the image.

That is not hypothetical. `ee7189e` shipped an orchestrator that copied
`config/`, `src/` and `pyproject.toml` and nothing else. The curated register
loaded empty, every policy question - `show me the sick leave policy` included -
answered "I could not find an approved policy on this topic in our handbook",
and `/health` said HEALTHY throughout. From the outside it was indistinguishable
from a handbook that genuinely does not cover sick leave.

These are static assertions over the Dockerfiles. They need no daemon and no
build, which is the point: they run in the same suite as everything else.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]

#: The images that serve application traffic. Each one answers policy questions,
#: so each one needs the handbook. `Dockerfile.saas_adapter` is excluded
#: deliberately - it is a FastMCP transport shim and holds no grounding.
SERVING_IMAGES = ("Dockerfile", "Dockerfile.orchestrator", "Dockerfile.policy_rag")


def _text(name: str) -> str:
    path = _REPO_ROOT / name
    assert path.exists(), f"{name} is missing from the repository root"
    return path.read_text()


def _joined(name: str) -> str:
    """The file as the builder sees it, with `\\`-continuations collapsed."""
    return re.sub(r"\\\n", "", _text(name))


@pytest.mark.parametrize("image", SERVING_IMAGES)
def test_the_image_ships_the_policy_corpus(image):
    """The single line whose absence caused the outage."""
    assert "COPY okf/" in _text(image), (
        f"{image} does not copy okf/ - every policy question in the resulting "
        "image will answer 'I could not find an approved policy on this topic'"
    )


@pytest.mark.parametrize("image", SERVING_IMAGES)
def test_the_image_ships_the_source_handbook(image):
    """The corpus cites into it, and the RAG indexes it alongside `okf/`."""
    assert "ALTOSTRAT SINGAPORE EMPLOYEE POLICY HANDBOOK" in _text(image), (
        f"{image} does not copy the handbook markdown"
    )


@pytest.mark.parametrize("image", SERVING_IMAGES)
def test_the_build_fails_when_the_corpus_is_absent(image):
    """A `COPY` that silently matches nothing is still a passing build.

    So the images assert the register is non-empty at build time. Without this
    the only signal is a production answer that looks like a legitimate refusal.
    """
    joined = _joined(image)
    guard = [line for line in joined.splitlines() if line.startswith("RUN python -c")]

    assert guard, f"{image} has no build-time corpus assertion"
    assert "okf_store.all_policies()" in guard[0]
    assert "SystemExit" in guard[0], (
        f"{image} checks the corpus but does not fail the build on an empty one"
    )


@pytest.mark.parametrize("image", SERVING_IMAGES)
def test_the_corpus_check_is_not_soft_failed(image):
    """`|| true` on the ingest is deliberate - the HF Hub rate-limits builds and
    the index is rebuilt at runtime. `|| true` on the corpus check would restore
    exactly the silence this file exists to prevent."""
    for line in _joined(image).splitlines():
        if line.startswith("RUN python -c") and "all_policies" in line:
            assert "|| true" not in line, f"{image}: the corpus check must be hard"


@pytest.mark.parametrize("image", SERVING_IMAGES)
def test_the_corpus_is_copied_before_it_is_checked(image):
    """Docker runs instructions in order; a check above the COPY always fails."""
    joined = _joined(image)
    # Both are asserted by the tests above; repeated here so that a missing one
    # reports itself rather than surfacing as `ValueError: substring not found`.
    assert "COPY okf/" in joined, f"{image} does not copy okf/"
    check = [
        line for line in joined.splitlines()
        if line.startswith("RUN python -c") and "all_policies" in line
    ]
    assert check, f"{image} has no build-time corpus assertion"

    assert joined.index("COPY okf/") < joined.index(check[0]), (
        f"{image} checks the corpus before copying it - the build always fails"
    )


def test_the_corpus_the_images_copy_actually_exists():
    """The assertions above are about a path. This is about the bytes."""
    corpus = _REPO_ROOT / "okf" / "altostrat-sg-handbook"

    assert corpus.is_dir(), "okf/altostrat-sg-handbook/ is missing"
    assert list(corpus.rglob("*.md")), "the corpus directory holds no markdown"


def test_the_sick_leave_policy_is_in_the_corpus():
    """The question that surfaced the outage, pinned as a canary.

    Named explicitly rather than folded into a count: a corpus that loses this
    one file still passes a "some markdown exists" check.
    """
    policy = _REPO_ROOT / "okf" / "altostrat-sg-handbook" / "leave" / "sick-and-hospitalisation.md"

    assert policy.exists(), "the sick leave policy is not in the corpus"
    assert policy.read_text().strip(), "the sick leave policy is empty"
