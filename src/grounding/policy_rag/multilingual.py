"""Language handling delegated to Gemini, with the script census as a floor.

`language.py` answers "what script is this?" by counting Unicode ranges. That is
cheap, dependency-free and correct for the four languages it was written for -
and it is also a *closed list*. Its `SUPPORTED_LANGUAGES` tuple named five codes,
`resolve` rejected anything outside it, and `detect` reported every language it
had no character range for - Thai, Vietnamese, Tamil, French, Bahasa - as
English. An Altostrat Singapore employee typing Malay got an English answer to a
question the system had not understood it had failed to read.

The limit was never a property of the problem. It was a property of hand-written
character tables, and Gemini already knows every language those tables were
trying to enumerate. So this module puts a model where the tables were:

* `understand()` - one Gemini 3.7 Flash call that reports the language of a
  query as a BCP-47 tag, from no fixed list, *and* renders the query into
  English. The second half is the part that makes non-English work rather than
  merely be detected: the index is embedded with `bge-small-en-v1.5`, an
  English-only model, so a Chinese question embedded as-is lands nowhere near
  the Chinese-free chunk that answers it. Retrieval runs on the English
  rendering; the user still reads their own language.
* `localize()` - the fixed strings (refusals, notices) in the user's language.

Both degrade to the old behaviour rather than failing. Gemini is unreachable in
CI and from a developer laptop without credentials, and a policy service that
stops answering English questions because a translation endpoint is down is a
worse outcome than the one this module exists to fix. When the call fails,
`understand` falls back to `language.detect` and to searching the raw query -
exactly what happened before this module existed - and `localize` returns the
English string. Every fallback is logged and reported in `Understanding.source`,
because "answered in English because detection failed" and "answered in English
because the question was English" are different events to an auditor.

Set `POLICY_RAG_LANGUAGE_SERVICE=off` to pin the heuristic path - the evaluation
harness does this so a golden set stays reproducible across model revisions.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from dataclasses import dataclass

from src.grounding.policy_rag.language import CORPUS_LANGUAGE, Language, resolve

logger = logging.getLogger(__name__)

#: Gemini 3.7 Flash is what the rest of the system routes on
#: (`src/integrations/vertex/client.py`, the four specialist agents), and this is
#: the same class of task: short, structured, latency-sensitive, on the critical
#: path of every query. Keeping one model across the language layer and the
#: router means a query is read the same way twice.
DEFAULT_MODEL = "gemini-3.7-flash"
MODEL_ENV_VAR = "POLICY_RAG_LANGUAGE_MODEL"
ENABLED_ENV_VAR = "POLICY_RAG_LANGUAGE_SERVICE"

#: Bound on what is cached. Queries repeat heavily - the same handful of leave
#: questions in the same handful of languages - but the key is user text, so it
#: cannot be allowed to grow without limit.
_CACHE_LIMIT = 512

_UNDERSTAND_INSTRUCTION = (
    "You prepare employee questions for an English-language HR policy search index.\n"
    "Return JSON with exactly two keys:\n"
    '  "language": the BCP-47 tag of the language the question is written in '
    '(e.g. "en", "zh-Hant", "ja", "ko", "th", "ms", "ta", "fr"). Use any tag that '
    "fits; you are not restricted to a list. Judge by the language, not by the "
    "script alone.\n"
    '  "english_query": the question rendered in English, as a search query.\n'
    "Rules:\n"
    "1. Preserve every number, date, currency amount, section number and proper "
    "noun exactly. They are what the search matches on.\n"
    "2. Translate meaning, not words. 病假 is 'sick leave', not 'sick vacation'.\n"
    "3. If the question is already English, copy it into english_query unchanged.\n"
    "4. Never answer the question. Never add information it does not contain."
)

_LOCALIZE_INSTRUCTION = (
    "You translate short fixed messages from an HR assistant into the employee's "
    "language.\n"
    "Return JSON with exactly one key, \"text\", holding the translation.\n"
    "Rules:\n"
    "1. Preserve markdown, links, numbers, currency amounts and section numbers "
    "verbatim.\n"
    "1a. Copy any bracketed placeholder - [PHONE_1], [EMAIL_2], [INC0003562], "
    "[WW-LV-MCP] - through exactly as written. These are substituted for real "
    "values downstream; a rewritten one cannot be resolved and the employee sees "
    "the placeholder instead of their own data.\n"
    "2. Keep the register: plain, factual, addressed to an employee.\n"
    "3. Do not add, remove or soften any statement. If the message declines to "
    "answer, the translation declines to answer.\n"
    "4. If the target language is English, return the message unchanged."
)

#: Gemini is asked for JSON and normally returns it, but a fenced block is a
#: common enough deviation to be worth stripping rather than failing on.
_JSON_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$")


@dataclass(frozen=True)
class Understanding:
    """What the language layer worked out about a query."""

    #: BCP-47 tag. Not drawn from any fixed list - see the module docstring.
    language: Language

    #: What retrieval should actually search for: the English rendering of the
    #: query, or the query itself when it is already English or when the model
    #: was unreachable.
    search_text: str

    #: `gemini` or `heuristic` (the model was unavailable or disabled).
    #: Reported on the wire: an English answer to a Thai question means
    #: something different depending on which of these produced it.
    source: str

    #: The text the employee actually typed. Kept so `translated` can compare.
    query_text: str = ""

    @property
    def translated(self) -> bool:
        """Whether retrieval will run on different text than the user typed."""
        return self.search_text != self.query_text


def _heuristic(text: str, requested: str | None) -> Understanding:
    """What this package did before there was a model: script census, no rewrite."""
    return Understanding(
        language=resolve(text, requested),
        search_text=text,
        source="heuristic",
        query_text=text,
    )


def _is_corpus_language(tag: str) -> bool:
    """`en`, `en-SG` and `EN` are all the corpus language; `eng-ish` is not."""
    primary = tag.strip().lower().replace("_", "-").split("-")[0]
    return primary == CORPUS_LANGUAGE


class LanguageService:
    """One Gemini client for the language layer, built on first successful use.

    Construction is deferred and failure is absorbed: importing this module must
    not require credentials, and neither must the first query on a box that has
    none.
    """

    def __init__(self, model: str | None = None, client: object | None = None) -> None:
        self._model = model or os.environ.get(MODEL_ENV_VAR, "").strip() or DEFAULT_MODEL
        self._client = client
        self._client_attempted = client is not None
        self._cache: dict[tuple, object] = {}
        self._lock = threading.Lock()

    # --- plumbing -----------------------------------------------------------

    @property
    def enabled(self) -> bool:
        return os.environ.get(ENABLED_ENV_VAR, "on").strip().lower() not in {"off", "0", "false"}

    def _get_client(self):
        if not self._client_attempted:
            self._client_attempted = True
            try:
                from google import genai

                self._client = genai.Client()
            except Exception as exc:
                # No credentials, no package, no network. All mean "use the floor".
                logger.info("language model unavailable (%s); using script detection", exc)
                self._client = None
        return self._client

    def _generate_json(self, instruction: str, prompt: str) -> dict | None:
        client = self._get_client()
        if client is None:
            return None
        try:
            from google.genai import types

            response = client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=instruction,
                    temperature=0.0,
                    response_mime_type="application/json",
                ),
            )
            raw = _JSON_FENCE_RE.sub("", (response.text or "").strip())
            parsed = json.loads(raw)
        except Exception as exc:
            logger.warning("language model call failed (%s); falling back", exc)
            return None
        return parsed if isinstance(parsed, dict) else None

    def _cached(self, key: tuple, produce):
        with self._lock:
            if key in self._cache:
                return self._cache[key]
        value = produce()
        with self._lock:
            if len(self._cache) >= _CACHE_LIMIT:
                self._cache.clear()
            self._cache[key] = value
        return value

    # --- public API ---------------------------------------------------------

    def understand(self, text: str, requested: str | None = None) -> Understanding:
        """Read a query's language and render it into English for retrieval.

        `requested` still wins for the *answer* language - a caller holding an
        `Accept-Language` header knows the user's locale better than any amount
        of inspection of a three-word query - but the English rendering is asked
        for either way, because it is about the corpus, not about the user.
        """
        if not text or not text.strip():
            return _heuristic(text, requested)
        if not self.enabled:
            return _heuristic(text, requested)

        return self._cached(
            ("understand", text, requested), lambda: self._understand_uncached(text, requested)
        )

    def _understand_uncached(self, text: str, requested: str | None) -> Understanding:
        parsed = self._generate_json(_UNDERSTAND_INSTRUCTION, text)
        if parsed is None:
            return _heuristic(text, requested)

        detected = str(parsed.get("language") or "").strip()
        english = str(parsed.get("english_query") or "").strip()
        if not detected:
            return _heuristic(text, requested)

        # The caller's tag governs what the employee reads; the model's reading
        # governs whether a translation was needed at all.
        tag = (requested or "").strip() or detected
        language = Language(tag, cross_lingual=not _is_corpus_language(tag))

        # An empty or unchanged rendering is not a failure - it is what an
        # English question produces - but searching on nothing certainly is.
        search_text = english or text
        return Understanding(
            language=language, search_text=search_text, source="gemini", query_text=text
        )

    def localize(self, text: str, language: Language | str | None) -> str:
        """Render a fixed message in the employee's language, or leave it alone.

        Used for refusals and guard notices. These are the sentences that matter
        most to get into the right language: a refusal the employee cannot read
        is indistinguishable from a broken service, and it is the response they
        are most likely to receive when something has already gone wrong.
        """
        tag = str(language) if language is not None else CORPUS_LANGUAGE
        if not text or _is_corpus_language(tag) or not self.enabled:
            return text
        translated = self._cached(
            ("localize", text, tag), lambda: self._localize_uncached(text, tag)
        )
        return translated or text

    def _localize_uncached(self, text: str, tag: str) -> str | None:
        parsed = self._generate_json(
            _LOCALIZE_INSTRUCTION, f"Target language: {tag}\n\nMessage:\n{text}"
        )
        if parsed is None:
            return None
        return str(parsed.get("text") or "").strip() or None


#: Process-wide instance. Callers may construct their own - the tests do - but
#: the cache is only worth having if it is shared.
language_service = LanguageService()


def understand(text: str, requested: str | None = None) -> Understanding:
    """Module-level shorthand for `language_service.understand`."""
    return language_service.understand(text, requested)


def localize(text: str, language: Language | str | None) -> str:
    """Module-level shorthand for `language_service.localize`."""
    return language_service.localize(text, language)
