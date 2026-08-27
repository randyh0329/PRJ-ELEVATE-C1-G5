"""Typed view over `config/corpus.yaml`."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

#: Repo root, i.e. the directory holding `okf/` and the handbook markdown.
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = REPO_ROOT / "policy-rag" / "config" / "corpus.yaml"

#: Entitlement granted to every authenticated employee.
GENERAL_ENTITLEMENT = "general"


@dataclass
class EmbeddingConfig:
    provider: str = "local"
    model: str = "sentence-transformers/all-MiniLM-L6-v2"
    dimension: int = 384
    batch_size: int = 64


@dataclass
class IndexConfig:
    path: Path = REPO_ROOT / "policy-rag" / "var" / "index"
    type: str = "flat"
    hnsw_m: int = 32


@dataclass
class ChunkingConfig:
    max_chars: int = 1400
    overlap_chars: int = 160
    min_chars: int = 80


@dataclass
class RetrievalConfig:
    top_k: int = 6
    candidate_k: int = 40
    relevance_gate: float = 0.80
    #: Strength of the lexical corroboration bonus. See `Retriever._fuse`.
    lexical_boost: float = 0.35
    #: Cosine below which a hit scores 0 and above which it scores 1. Both are
    #: properties of the embedding model, not of the corpus - re-derive them with
    #: `scripts/eval_retrieval.py --sweep` whenever `embedding.model` changes.
    cosine_floor: float = 0.50
    cosine_ceiling: float = 0.82
    max_chunks_per_document: int = 3
    default_doc_types: list[str] = field(
        default_factory=lambda: ["policy", "datasheet", "computation", "reference", "skill"]
    )


@dataclass
class AclOverride:
    path_prefix: str
    entitlement: str


@dataclass
class CorpusConfig:
    id: str
    kind: str  # okf | handbook
    authority: str  # governing | source
    default_search: bool
    default_entitlement: str = GENERAL_ENTITLEMENT
    root: str | None = None
    path: str | None = None
    acl_overrides: list[AclOverride] = field(default_factory=list)

    def entitlement_for(self, relative_path: str) -> str:
        for override in self.acl_overrides:
            if relative_path.startswith(override.path_prefix):
                return override.entitlement
        return self.default_entitlement


@dataclass
class GuardConfig:
    conflict_sections: bool = True
    extended_workforce_leave: bool = True
    placeholder_contacts: bool = True
    staleness: bool = True
    escalation_contact: str = "People Ops"


@dataclass
class Config:
    embedding: EmbeddingConfig
    index: IndexConfig
    chunking: ChunkingConfig
    retrieval: RetrievalConfig
    guards: GuardConfig
    corpora: list[CorpusConfig]
    repo_root: Path = REPO_ROOT

    def corpus(self, corpus_id: str) -> CorpusConfig:
        for c in self.corpora:
            if c.id == corpus_id:
                return c
        raise KeyError(f"unknown corpus: {corpus_id!r}")

    @property
    def default_corpora(self) -> list[str]:
        return [c.id for c in self.corpora if c.default_search]


def load_config(path: str | os.PathLike[str] | None = None) -> Config:
    """Read the YAML config, applying `POLICY_RAG_*` environment overrides.

    Environment overrides exist so the same config file works in CI (where the
    `hash` embedder avoids a model download) and in a container image where the
    index lives on a mounted volume.
    """
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    raw: dict[str, Any] = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}

    emb_raw = raw.get("embedding", {})
    embedding = EmbeddingConfig(
        provider=os.environ.get("POLICY_RAG_EMBEDDING_PROVIDER", emb_raw.get("provider", "local")),
        model=os.environ.get("POLICY_RAG_EMBEDDING_MODEL", emb_raw.get("model", EmbeddingConfig.model)),
        dimension=int(emb_raw.get("dimension", 384)),
        batch_size=int(emb_raw.get("batch_size", 64)),
    )

    idx_raw = raw.get("index", {})
    index_path = os.environ.get("POLICY_RAG_INDEX_PATH") or idx_raw.get("path", "var/index")
    index_path_obj = Path(index_path)
    if not index_path_obj.is_absolute():
        index_path_obj = cfg_path.parent.parent / index_path_obj
    index = IndexConfig(
        path=index_path_obj,
        type=idx_raw.get("type", "flat"),
        hnsw_m=int(idx_raw.get("hnsw_m", 32)),
    )

    chunk_raw = raw.get("chunking", {})
    chunking = ChunkingConfig(
        max_chars=int(chunk_raw.get("max_chars", 1400)),
        overlap_chars=int(chunk_raw.get("overlap_chars", 160)),
        min_chars=int(chunk_raw.get("min_chars", 80)),
    )

    ret_raw = raw.get("retrieval", {})
    calib = ret_raw.get("calibration", {})
    retrieval = RetrievalConfig(
        top_k=int(ret_raw.get("top_k", 6)),
        candidate_k=int(ret_raw.get("candidate_k", 40)),
        relevance_gate=float(os.environ.get("POLICY_RAG_RELEVANCE_GATE", ret_raw.get("relevance_gate", 0.80))),
        lexical_boost=float(ret_raw.get("lexical_boost", 0.35)),
        cosine_floor=float(calib.get("cosine_floor", 0.50)),
        cosine_ceiling=float(calib.get("cosine_ceiling", 0.82)),
        max_chunks_per_document=int(ret_raw.get("max_chunks_per_document", 3)),
        default_doc_types=list(ret_raw.get("default_doc_types", RetrievalConfig().default_doc_types)),
    )

    guard_raw = raw.get("guards", {})
    guards = GuardConfig(
        conflict_sections=bool(guard_raw.get("conflict_sections", True)),
        extended_workforce_leave=bool(guard_raw.get("extended_workforce_leave", True)),
        placeholder_contacts=bool(guard_raw.get("placeholder_contacts", True)),
        staleness=bool(guard_raw.get("staleness", True)),
        escalation_contact=guard_raw.get("escalation_contact", "People Ops"),
    )

    corpora: list[CorpusConfig] = []
    for entry in raw.get("corpora", []):
        acl = entry.get("acl", {})
        corpora.append(
            CorpusConfig(
                id=entry["id"],
                kind=entry["kind"],
                authority=entry.get("authority", "governing"),
                default_search=bool(entry.get("default_search", True)),
                default_entitlement=acl.get("default", GENERAL_ENTITLEMENT),
                root=entry.get("root"),
                path=entry.get("path"),
                acl_overrides=[
                    AclOverride(path_prefix=o["path_prefix"], entitlement=o["entitlement"])
                    for o in acl.get("overrides", [])
                ],
            )
        )

    return Config(
        embedding=embedding,
        index=index,
        chunking=chunking,
        retrieval=retrieval,
        guards=guards,
        corpora=corpora,
    )
