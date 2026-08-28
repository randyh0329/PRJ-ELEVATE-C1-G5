"""The ingest build: load -> chunk -> embed -> verify -> publish (SDD §3.2.1, §4.7).

The behaviour worth pinning here is not that a good corpus builds - the session
fixtures already prove that - but that a *bad* one does not get published. Every
failure mode below raises before `index.save`, because an index that is empty,
mis-embedded or unable to answer its own canary probes turns a retrieval defect
into a confidently wrong answer in production.

Everything runs on the hermetic `hash` provider over a two-file corpus in
`tmp_path`, so no test here touches the real `var/index`.
"""

from __future__ import annotations

import copy
import hashlib

import numpy as np
import pytest

from src.grounding.policy_rag import ingest as ingest_module
from src.grounding.policy_rag.config import Config, CorpusConfig, EmbeddingConfig
from src.grounding.policy_rag.documents import Document
from src.grounding.policy_rag.embeddings import build_provider
from src.grounding.policy_rag.index import PolicyIndex
from src.grounding.policy_rag.ingest import (
    IngestReport,
    build_chunks,
    collect_documents,
    detect_drift,
    ingest,
    verify_index,
)

VACATION = """---
type: HR policy
title: Vacation Leave
status: stable
---

# Accrual

Employees accrue fourteen days of paid vacation leave for each completed year of
continuous service, credited monthly in arrears.
"""

SICK = """---
type: HR policy
title: Sick Leave
status: stable
---

# Outpatient

Employees are entitled to fourteen days of outpatient sick leave per calendar
year once they have completed six months of continuous service.
"""

STUB = """---
type: HR policy
title: Reserved
---

# Reserved

Reserved.
"""


@pytest.fixture
def mini(config, tmp_path) -> Config:
    """A two-document OKF bundle in its own repo root, indexed to `tmp_path`."""
    cfg = copy.deepcopy(config)
    cfg.repo_root = tmp_path
    cfg.index.path = tmp_path / "index"
    cfg.corpora = [
        CorpusConfig(id="mini", kind="okf", authority="governing", default_search=True, root="bundle")
    ]
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "vacation.md").write_text(VACATION, encoding="utf-8")
    (bundle / "sick.md").write_text(SICK, encoding="utf-8")
    return cfg


def _document(**overrides) -> Document:
    base = {
        "doc_id": "doc-1",
        "corpus_id": "mini",
        "path": "bundle/vacation.md",
        "title": "Vacation Leave",
        "doc_type": "policy",
        "authority": "governing",
        "entitlement": "general",
        "body": "# Accrual\n\n" + "Employees accrue fourteen days of paid vacation leave each year. " * 2,
    }
    base.update(overrides)
    return Document(**base)


# --- the report ---------------------------------------------------------------


def test_the_report_renders_its_counts_and_provenance():
    rendered = IngestReport(
        documents=2,
        chunks=5,
        by_corpus={"mini": 5},
        by_doc_type={"policy": 5},
        index_path="/tmp/index",
        embedder="hash:384",
    ).render()

    assert "Indexed 5 chunks from 2 documents" in rendered
    assert "embedder : hash:384" in rendered
    assert "index    : /tmp/index" in rendered
    assert "mini" in rendered
    assert "policy" in rendered
    assert "produced no chunks" not in rendered


def test_the_report_names_the_documents_that_produced_nothing():
    """A file that silently contributes zero chunks is indistinguishable from one
    that was never in the corpus, so the build has to say which."""
    rendered = IngestReport(skipped_empty=["bundle/index.md", "bundle/log.md"]).render()

    assert "produced no chunks (2):" in rendered
    assert "bundle/index.md" in rendered
    assert "bundle/log.md" in rendered


# --- chunking the corpus ------------------------------------------------------


def test_a_document_too_short_to_chunk_is_reported_not_dropped(config):
    chunks, skipped = build_chunks(config, [_document(), _document(doc_id="doc-2", body="Too short.")])

    assert skipped == ["bundle/vacation.md"]
    assert chunks and all(c.doc_id == "doc-1" for c in chunks)


def test_a_duplicate_chunk_id_fails_the_build(config):
    """Chunk ids are content-addressed on (doc_id, headings, ordinal). A collision
    means the derivation is not unique, and the second chunk would overwrite the
    first in the index - a policy paragraph silently missing from retrieval."""
    twin = _document()

    with pytest.raises(ValueError, match="duplicate chunk id"):
        build_chunks(config, [twin, copy.deepcopy(twin)])


def test_collect_documents_concatenates_every_declared_corpus(mini):
    assert sorted(d.path for d in collect_documents(mini)) == ["bundle/sick.md", "bundle/vacation.md"]


# --- the canary probes --------------------------------------------------------


def test_a_probe_that_retrieves_its_document_passes(config, index):
    """Run at gate 0: under the hash provider nothing clears the production gate,
    so at 0.80 this would fail for a reason that has nothing to do with the index."""
    open_gate = copy.deepcopy(config)
    open_gate.retrieval.relevance_gate = 0.0

    verify_index(
        open_gate,
        index,
        build_provider(open_gate.embedding),
        [("how much paid vacation leave do I accrue", "okf/")],
    )


def test_a_probe_the_index_cannot_answer_fails_the_build(config, index):
    with pytest.raises(RuntimeError, match="index verification probe failed") as excinfo:
        verify_index(
            config,
            index,
            build_provider(config.embedding),
            [("how much paid vacation leave do I accrue", "nowhere/at-all.md")],
        )

    message = str(excinfo.value)
    assert "nowhere/at-all.md" in message
    # The best score the gate saw is the first thing an operator needs; without
    # it "gate rejected everything" gives no way to tell a mis-embedded index
    # from a gate set too high.
    assert "best relevance" in message


def test_every_default_probe_names_a_corpus_document(documents):
    """A probe pointing at a path the corpus no longer has would fail every build
    for a reason that is not a defect in the index."""
    paths = [d.path for d in documents]

    for _query, fragment in ingest_module.DEFAULT_PROBES:
        assert any(fragment in p for p in paths), fragment


# --- a full build -------------------------------------------------------------


def test_a_full_ingest_writes_an_index_that_loads_back(mini):
    report = ingest(mini)

    assert report.documents == 2
    assert report.chunks >= 2
    assert report.by_corpus == {"mini": report.chunks}
    assert report.by_doc_type == {"policy": report.chunks}
    assert report.skipped_empty == []
    assert report.index_path == str(mini.index.path)

    reloaded = PolicyIndex.load(mini.index.path)
    assert len(reloaded) == report.chunks
    assert reloaded.manifest.embedder_fingerprint == report.embedder
    assert reloaded.manifest.document_count == 2


def test_the_manifest_records_a_digest_of_every_source_file(mini):
    """SLA-07 drift detection is offline: it compares these digests, so a source
    file missing from the manifest can change without anyone noticing."""
    ingest(mini)

    digests = PolicyIndex.load(mini.index.path).manifest.source_digests
    assert set(digests) == {"bundle/sick.md", "bundle/vacation.md"}
    on_disk = (mini.repo_root / "bundle" / "vacation.md").read_bytes()
    assert digests["bundle/vacation.md"] == hashlib.sha256(on_disk).hexdigest()


def test_a_document_with_no_file_behind_it_is_left_out_of_the_digests(mini, monkeypatch):
    """A loader may synthesise a document (the handbook emits several per file, a
    future one could emit one per API record). Digesting `repo_root / path` blind
    would raise on those; skipping them costs only drift detection for that path."""
    monkeypatch.setattr(
        ingest_module, "load_corpus", lambda corpus, root: [_document(path="virtual/not-on-disk.md")]
    )

    ingest(mini)

    manifest = PolicyIndex.load(mini.index.path).manifest
    assert manifest.source_digests == {}
    assert manifest.chunk_count >= 1


def test_an_ingest_that_produces_no_chunks_publishes_nothing(mini):
    """An empty index answers every question with a refusal. Publishing one would
    look like a corpus with nothing to say rather than a broken build."""
    for name in ("vacation.md", "sick.md"):
        (mini.repo_root / "bundle" / name).write_text(STUB, encoding="utf-8")

    with pytest.raises(RuntimeError, match="produced no chunks"):
        ingest(mini)

    assert not mini.index.path.exists()


def test_an_embedder_returning_the_wrong_vector_count_fails_the_build(mini, monkeypatch):
    """Chunks and vectors are zipped by position downstream, so a length mismatch
    would attach every citation to the wrong passage."""

    class _Truncating:
        name = "truncating"
        dimension = 4

        def fingerprint(self) -> str:
            return "truncating:4"

        def encode(self, texts: list[str]) -> np.ndarray:
            return np.zeros((len(texts) - 1, self.dimension), dtype=np.float32)

    monkeypatch.setattr(ingest_module, "build_provider", lambda cfg: _Truncating())

    with pytest.raises(RuntimeError, match="wrong number of vectors"):
        ingest(mini)

    assert not mini.index.path.exists()


def test_the_hash_provider_is_exempt_from_the_probes(mini, caplog):
    """The hash embedder carries no semantic signal, so holding it to a retrieval
    probe would fail every hermetic build. The exemption is logged, loudly."""
    with caplog.at_level("WARNING", logger="src.grounding.policy_rag.ingest"):
        ingest(mini)

    assert "skipping verification probes" in caplog.text


def test_a_real_embedder_is_held_to_the_probes(mini, monkeypatch):
    """Anything that is not the hash fixture must answer the canaries, and a build
    that cannot must not reach `index.save`."""
    mini.embedding.provider = "local"
    hermetic = EmbeddingConfig(provider="hash", model="hash")
    monkeypatch.setattr(ingest_module, "build_provider", lambda cfg: build_provider(hermetic))

    with pytest.raises(RuntimeError, match="index verification probe failed"):
        ingest(mini)

    assert not mini.index.path.exists()


def test_verification_can_be_turned_off_for_a_deliberate_partial_build(mini, monkeypatch, caplog):
    mini.embedding.provider = "local"
    hermetic = EmbeddingConfig(provider="hash", model="hash")
    monkeypatch.setattr(ingest_module, "build_provider", lambda cfg: build_provider(hermetic))

    with caplog.at_level("WARNING", logger="src.grounding.policy_rag.ingest"):
        report = ingest(mini, verify=False)

    assert report.chunks >= 2
    assert "skipping verification probes" not in caplog.text
    assert (mini.index.path / "faiss.index").is_file()


# --- drift against the built index --------------------------------------------


def test_an_untouched_corpus_has_not_drifted(mini):
    ingest(mini)

    assert detect_drift(mini) == []


def test_an_edited_source_file_is_reported_as_modified(mini):
    ingest(mini)
    (mini.repo_root / "bundle" / "vacation.md").write_text(
        VACATION.replace("fourteen days", "twenty-one days"), encoding="utf-8"
    )

    assert detect_drift(mini) == ["bundle/vacation.md (modified)"]


def test_a_deleted_source_file_is_reported_as_deleted(mini):
    ingest(mini)
    (mini.repo_root / "bundle" / "sick.md").unlink()

    assert detect_drift(mini) == ["bundle/sick.md (deleted)"]


def test_a_new_source_file_is_reported_as_new(mini):
    """The index cannot answer from a policy it has never seen; the drift check is
    the only thing that says so without a rebuild."""
    ingest(mini)
    (mini.repo_root / "bundle" / "bereavement.md").write_text(
        VACATION.replace("Vacation", "Bereavement"), encoding="utf-8"
    )

    assert detect_drift(mini) == ["bundle/bereavement.md (new)"]
