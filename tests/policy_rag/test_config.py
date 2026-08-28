"""`config/corpus.yaml` and the typed view over it.

The config file is the single declaration of what is ingested and who may
retrieve it, so the tests that matter here are the ones about a *wrong* config:
an unknown corpus id, an environment override that silently does nothing.
"""

from __future__ import annotations

import textwrap

import pytest

from src.grounding.policy_rag.config import (
    DEFAULT_CONFIG_PATH,
    AclOverride,
    CorpusConfig,
    load_config,
)

MINIMAL = """\
embedding:
  provider: local
  model: BAAI/bge-small-en-v1.5
index:
  path: var/index
corpora:
  - id: okf-handbook
    kind: okf
    root: okf/altostrat-sg-handbook
    authority: governing
    default_search: true
    acl:
      default: general
      overrides:
        - path_prefix: references/
          entitlement: hr_operational
  - id: handbook-source
    kind: handbook
    path: handbook.md
    authority: source
    default_search: false
"""


@pytest.fixture
def written(tmp_path):
    """The minimal config above, laid out as `<root>/config/corpus.yaml`."""

    def _write(body: str = MINIMAL):
        config_dir = tmp_path / "config"
        config_dir.mkdir(exist_ok=True)
        path = config_dir / "corpus.yaml"
        path.write_text(textwrap.dedent(body), encoding="utf-8")
        return path

    return _write


# --- lookup -------------------------------------------------------------------


def test_a_corpus_is_found_by_id(written):
    cfg = load_config(written())

    assert cfg.corpus("handbook-source").kind == "handbook"


def test_an_unknown_corpus_id_is_a_keyerror(written):
    """Nothing may introduce a corpus at runtime, so a caller naming one that is
    not declared has to fail rather than fall back to the default set."""
    cfg = load_config(written())

    with pytest.raises(KeyError, match="unknown corpus: 'notion'"):
        cfg.corpus("notion")


def test_the_default_search_set_excludes_the_raw_handbook(written):
    """SDD §4.7: searching the OKF bundle and its own source together would
    reintroduce the two-layer conflict the bundle exists to resolve."""
    assert load_config(written()).default_corpora == ["okf-handbook"]


# --- entitlements -------------------------------------------------------------


def test_an_acl_override_wins_over_the_corpus_default(written):
    okf = load_config(written()).corpus("okf-handbook")

    assert okf.entitlement_for("references/source-defects.md") == "hr_operational"
    assert okf.entitlement_for("leave/vacation.md") == "general"


def test_a_corpus_with_no_overrides_grants_its_default_everywhere():
    corpus = CorpusConfig(
        id="mini", kind="okf", authority="governing", default_search=True, default_entitlement="hr_operational"
    )

    assert corpus.entitlement_for("anything.md") == "hr_operational"


def test_the_first_matching_override_is_the_one_that_applies():
    corpus = CorpusConfig(
        id="mini",
        kind="okf",
        authority="governing",
        default_search=True,
        acl_overrides=[
            AclOverride(path_prefix="references/", entitlement="hr_operational"),
            AclOverride(path_prefix="references/public/", entitlement="general"),
        ],
    )

    assert corpus.entitlement_for("references/public/faq.md") == "hr_operational"


# --- paths and environment overrides ------------------------------------------


def test_a_relative_index_path_resolves_against_the_repo_root(written):
    path = written()

    cfg = load_config(path)

    assert cfg.index.path == path.parent.parent / "var" / "index"


def test_an_absolute_index_path_is_taken_verbatim(written, tmp_path, monkeypatch):
    """The container image mounts the index on a volume; rewriting that path
    relative to the repo would point the service at an empty directory."""
    mounted = tmp_path / "mnt" / "index"
    monkeypatch.setenv("POLICY_RAG_INDEX_PATH", str(mounted))

    assert load_config(written()).index.path == mounted


def test_the_embedder_can_be_swapped_for_ci(written, monkeypatch):
    """CI runs the hash provider so no model is downloaded; the same file serves
    both, which only works if the override actually takes."""
    monkeypatch.setenv("POLICY_RAG_EMBEDDING_PROVIDER", "hash")
    monkeypatch.setenv("POLICY_RAG_EMBEDDING_MODEL", "hash")

    cfg = load_config(written())

    assert (cfg.embedding.provider, cfg.embedding.model) == ("hash", "hash")


def test_the_relevance_gate_can_be_overridden(written, monkeypatch):
    monkeypatch.setenv("POLICY_RAG_RELEVANCE_GATE", "0.5")

    assert load_config(written()).retrieval.relevance_gate == 0.5


def test_an_empty_config_file_falls_back_to_the_dataclass_defaults(written):
    cfg = load_config(written("# nothing declared\n"))

    assert cfg.corpora == []
    assert cfg.embedding.provider == "local"
    assert cfg.retrieval.relevance_gate == 0.80
    assert cfg.guards.escalation_contact == "People Ops"


# --- the file the service actually ships with ---------------------------------


def test_the_shipped_config_declares_both_corpora():
    cfg = load_config()

    assert DEFAULT_CONFIG_PATH.is_file()
    assert {c.id for c in cfg.corpora} == {"okf-handbook", "handbook-source"}
    assert cfg.retrieval.relevance_gate >= 0.80
    assert cfg.corpus("okf-handbook").entitlement_for("references/") == "hr_operational"
