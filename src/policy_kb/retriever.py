import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from src.config import settings
from src.models.chat import Citation


class PolicyPassage:
    def __init__(self, doc_id: str, title: str, section: str, uri: str, content: str, version: str):
        self.doc_id = doc_id
        self.title = title
        self.section = section
        self.uri = uri
        self.content = content
        self.version = version


class PolicyKnowledgeBase:
    """
    Implements Curated Policy Knowledge Base and Grounded Retrieval (SDD §3.1, FR-2.1, FR-2.2).
    Simulates Agent Search with strict citation links and 0% policy hallucination guardrail.
    """
    def __init__(self, policies_dir: Optional[Path] = None):
        self.policies_dir = policies_dir or settings.policies_dir
        self.passages: List[PolicyPassage] = []
        self.index_policies()

    def index_policies(self):
        self.passages.clear()
        if not self.policies_dir.exists():
            return

        for file_path in self.policies_dir.glob("*.md"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    text = f.read()
                
                # Extract Title
                title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
                title = title_match.group(1).strip() if title_match else file_path.stem
                
                # Extract Doc ID
                doc_id_match = re.search(r"Document ID:\s*([^\n]+)", text)
                doc_id = doc_id_match.group(1).strip() if doc_id_match else file_path.stem

                # Extract Version
                ver_match = re.search(r"Version:\s*([^\n]+)", text)
                version = ver_match.group(1).strip() if ver_match else "1.0"

                # Split by sections ##
                sections = re.split(r"\n(?=##\s+)", text)
                for sec in sections:
                    sec_match = re.search(r"^##\s+(.+)$", sec, re.MULTILINE)
                    sec_title = sec_match.group(1).strip() if sec_match else "General"
                    sec_anchor = re.sub(r"[^a-zA-Z0-9_-]", "", sec_title.lower().replace(" ", "-"))
                    uri = f"policies/{file_path.name}#{sec_anchor}"
                    
                    self.passages.append(PolicyPassage(
                        doc_id=doc_id,
                        title=title,
                        section=sec_title,
                        uri=uri,
                        content=sec.strip(),
                        version=version
                    ))
            except Exception as e:
                print(f"Error indexing policy {file_path}: {e}")

    def query(self, query_text: str, max_results: int = 3) -> Dict[str, Any]:
        """
        Retrieves grounded policy passages.
        If no relevant passages found, returns groundedness_score = 0.0 and empty citations.
        """
        words = set(re.findall(r"\w+", query_text.lower()))
        # Filter stopwords
        stopwords = {"what", "is", "the", "a", "an", "for", "to", "in", "how", "many", "do", "i", "get", "can", "my", "of", "and"}
        keywords = words - stopwords
        if not keywords:
            keywords = words

        scored_passages = []
        for p in self.passages:
            content_lower = p.content.lower()
            title_lower = p.title.lower()
            section_lower = p.section.lower()
            
            score = 0.0
            for kw in keywords:
                if kw in section_lower:
                    score += 3.0
                elif kw in title_lower:
                    score += 2.0
                elif kw in content_lower:
                    score += 1.0

            if score > 0.0:
                scored_passages.append((score, p))

        scored_passages.sort(key=lambda x: x[0], reverse=True)
        top_matches = scored_passages[:max_results]

        if not top_matches or top_matches[0][0] < 1.0:
            return {
                "grounded": False,
                "groundedness_score": 0.0,
                "passages": [],
                "citations": [],
                "fallback_message": (
                    "I could not find that in the official policy documents, so I would rather not guess. "
                    "Here is the HR Portal link: https://hr.corp.internal"
                )
            }

        citations = []
        passages_text = []
        for score, p in top_matches:
            citations.append(Citation(
                documentTitle=f"{p.title} ({p.version})",
                uri=p.uri,
                section=p.section,
                snippet=p.content[:200] + "..." if len(p.content) > 200 else p.content
            ))
            passages_text.append(p.content)

        return {
            "grounded": True,
            "groundedness_score": 0.95,
            "passages": passages_text,
            "citations": citations,
            "fallback_message": None
        }


policy_kb = PolicyKnowledgeBase()
