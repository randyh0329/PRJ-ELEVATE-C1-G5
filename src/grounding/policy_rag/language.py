"""Script detection and CJK-aware tokenisation.

The corpus is English. Employees are not - Altostrat Singapore staffs its
offices from Japan, Korea and Taiwan - so a question typed in Japanese has to
reach the same handbook paragraph an English one would.

Two assumptions about English were buried in this package, and both failed
silently rather than loudly:

* `retriever.tokenize` matched `[a-z0-9]+`, so a Japanese question produced *no*
  terms. A query with no terms scores 0.0 lexical overlap against every chunk,
  and `min_lexical_corroboration` reads 0.0 as "uncorroborated" and drops the
  hit. The result was not degraded retrieval, it was a categorical refusal of
  every CJK question ever asked, whatever the index contained.
* The guards trigger on English keyword lists. A Korean contractor asking about
  leave therefore walked straight past the `extended_workforce_leave`
  escalation - the guard that exists precisely to stop them being handed a
  number that does not apply to them. Accepting CJK input without translating
  the guards would have turned a refusal bug into a wrong-answer bug, which is
  the trade NFR-3.1 forbids.

Detection is a Unicode script census, not a statistical model. It runs on the
critical path of every query, it must not add a dependency, and the question it
actually has to answer - Han, kana or Hangul - is one a script census settles
outright. Where it is weak is separating languages that *share* a script; see
`detect` for the two cases that matter and how each is resolved.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

#: A caller-supplied language tag is accepted on *shape*, never on membership of
#: a list - see `resolve`. Primary subtag of 2-3 letters (ISO 639-1/-2/-3),
#: optionally followed by script, region, variant or singleton-extension
#: subtags: `en`, `ja-JP`, `zh-Hant`, `pt-BR`, `en-SG-x-corp`. Underscores are
#: tolerated because POSIX locales (`zh_TW`) reach HTTP handlers more often than
#: they should.
#:
#: The bound that does the work is on the *primary* subtag: no language on earth
#: has a four-letter one, which is what rejects `klingon` and `javascript` while
#: admitting every real tag without anyone maintaining a list of them.
BCP_47_RE = re.compile(r"^[A-Za-z]{2,3}([-_][A-Za-z0-9]{1,8})*$")

#: The language the indexed corpus is written in. Everything else is
#: "cross-lingual" and takes the carve-outs documented in `Retriever.retrieve`.
CORPUS_LANGUAGE = "en"

ENGLISH = "en"
JAPANESE = "ja"
KOREAN = "ko"
TRADITIONAL_CHINESE = "zh-Hant"
SIMPLIFIED_CHINESE = "zh-Hans"

#: The languages this census can *name*. Not a list of languages the service
#: supports, and no longer a gate on anything: `multilingual.resolve_tag` honours
#: any well-formed BCP-47 tag a caller supplies, and `multilingual.understand`
#: reads the language with Gemini, which is bounded by no list at all. What is
#: left here is the floor - what can still be worked out from character ranges
#: alone when the model is unreachable.
CENSUS_LANGUAGES = (ENGLISH, JAPANESE, KOREAN, TRADITIONAL_CHINESE, SIMPLIFIED_CHINESE)

#: Han text carrying no orthography-specific character is ambiguous between the
#: two Chinese scripts. Traditional is the tie-break because the Taiwan office is
#: the zh-reading population this service was extended for; a Simplified reader
#: can read the answer either way, since only the *answer language* turns on
#: this and retrieval does not.
AMBIGUOUS_HAN_DEFAULT = TRADITIONAL_CHINESE

# Spelled as escapes, not literals: several of these boundary characters are
# invisible or homoglyphs of ASCII punctuation, and a range that silently lost
# an endpoint to a copy-paste is not a failure any test would name.
_HAN = "\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"      # ideographs, ext A, compat
_KANA = "\u3040-\u309f\u30a0-\u30ff\u31f0-\u31ff\uff66-\uff9d"  # hiragana, katakana, halfwidth
_HANGUL = "\uac00-\ud7a3\u1100-\u11ff\u3130-\u318f"   # syllables, jamo, compat jamo

_HAN_RE = re.compile(f"[{_HAN}]")
_KANA_RE = re.compile(f"[{_KANA}]")
_HANGUL_RE = re.compile(f"[{_HANGUL}]")

#: Han runs and kana runs are bigrammed together: Japanese interleaves the two
#: inside a single word (`お問い合わせ`), and splitting on the script boundary
#: would cut exactly the compounds worth matching.
_CJK_RUN_RE = re.compile(f"[{_HAN}{_KANA}]+")
_HANGUL_RUN_RE = re.compile(f"[{_HANGUL}]+")

#: Kanji simplified by Japan alone. Present in neither Chinese orthography, so
#: each one is positive evidence of Japanese in text that has no kana - which is
#: the shape a terse query like `年次有給休暇` takes.
_JAPANESE_ONLY_KANJI = frozenset("働込峠畑匂辻枠塀栃凪榊樫麿円図発実気駅桜沢経済応労価営団帰観験売読単譲関数処県薬")

#: Words spelled with characters all three orthographies share, but only Japan
#: combines this way. `契約社員` and `年次有給休暇` are pure shared kanji and would
#: otherwise be read as Chinese; both are also among the most common things an
#: employee of an HR system types, so the shortlist earns its keep.
_JAPANESE_ONLY_WORDS = ("休暇", "有給", "社員", "手当", "残業", "退職", "勤務", "給与", "会社", "申込")

#: Characters that exist in one Chinese orthography and not the other. Only
#: consulted once Japanese has been ruled out, because Japanese shinjitai
#: overlaps heavily with the Traditional column - which is harmless in that
#: order, and would be a systematic misread in any other.
_SIMPLIFIED_ONLY = frozenset(
    "几个们这来国说时对开没样点儿华产业务员动义习书长门问题银见车东马龙头岁应经济发实气图"
    "请让语该认为关亲单现电话数战无处备报离职员导级结满亚广场专业务约"
)
_TRADITIONAL_ONLY = frozenset(
    "幾個們這來國說時對開沒樣點兒華產業務員動義習書長門問題銀見車東馬龍頭歲應經濟發實氣圖"
    "請讓語該認為關親單現電話數戰無處備報離職導級結滿亞廣場專約"
)


@dataclass(frozen=True)
class Language:
    """The detected language of a query, and what follows from it."""

    code: str
    #: True when the query is not in the corpus language, which is what the
    #: retrieval and grounding carve-outs key on.
    cross_lingual: bool

    def __str__(self) -> str:
        return self.code


def detect(text: str, *, default: str = ENGLISH) -> Language:
    """Classify `text` by Unicode script.

    Resolution order is Hangul, then Japanese, then Han, and the order is the
    point. Hangul is unambiguous. Japanese is checked before Chinese because the
    evidence for it - kana, or a kanji Japan simplified on its own - is
    *positive*, whereas "Han and nothing else" is merely the absence of evidence
    for anything more specific.

    Two limits worth stating rather than hiding. A query written wholly in kanji
    that Japan and Taiwan spell identically cannot be told apart from Chinese by
    any amount of character inspection, and is reported as `zh-Hant` per
    `AMBIGUOUS_HAN_DEFAULT`. And a query too short to contain a distinguishing
    character - `休暇?` - falls into the same bucket. Both misfire only on the
    *answer* language: retrieval is driven by the embedding, which does not
    consult this function at all.
    """
    if not text:
        return Language(default, cross_lingual=default != CORPUS_LANGUAGE)

    if _HANGUL_RE.search(text):
        return Language(KOREAN, cross_lingual=True)

    has_han = bool(_HAN_RE.search(text))
    if (
        _KANA_RE.search(text)
        or any(char in _JAPANESE_ONLY_KANJI for char in text)
        or any(word in text for word in _JAPANESE_ONLY_WORDS)
    ):
        return Language(JAPANESE, cross_lingual=True)

    if has_han:
        simplified = sum(char in _SIMPLIFIED_ONLY for char in text)
        traditional = sum(char in _TRADITIONAL_ONLY for char in text)
        if simplified > traditional:
            return Language(SIMPLIFIED_CHINESE, cross_lingual=True)
        if traditional > simplified:
            return Language(TRADITIONAL_CHINESE, cross_lingual=True)
        return Language(AMBIGUOUS_HAN_DEFAULT, cross_lingual=True)

    return Language(default, cross_lingual=default != CORPUS_LANGUAGE)


def resolve(text: str, requested: str | None = None) -> Language:
    """Honour an explicitly requested language, else detect one.

    A caller that already knows its user's locale should say so - a browser
    `Accept-Language` beats any amount of character counting on a two-word
    query.

    Any *well-formed* tag is honoured. This used to test membership of a
    five-code tuple, which threw away `ja-JP`, `zh-TW`, `pt-BR` and every other
    perfectly good locale in favour of guessing from characters - and guessing
    is exactly what the caller had just made unnecessary. Worse, the tuple was
    also the service's answer to "which languages does this support?", so
    extending support meant editing a list, and any language nobody had thought
    to add was silently answered in English.

    What replaces it is a shape check, not a shorter list. `BCP_47_RE` asks
    whether the string could be a language tag at all; it does not ask which
    language, because that question has thousands of right answers and no
    maintainable enumeration of them. Malformed input still falls through to
    detection rather than raising - the parameter is a presentation hint, and
    failing a policy question over a bad locale header would be a poor trade.
    """
    if requested:
        tag = requested.strip()
        if BCP_47_RE.match(tag):
            primary = tag.lower().replace("_", "-").split("-")[0]
            return Language(tag, cross_lingual=primary != CORPUS_LANGUAGE)
        if tag:
            logger.debug("ignoring malformed language tag %r; detecting instead", tag)
    return detect(text)


def cjk_terms(text: str) -> list[str]:
    """Character bigrams over each contiguous CJK run.

    CJK is not space-delimited, and a real segmenter (MeCab, mecab-ko, jieba)
    means a per-language dictionary, a model download and a language guess made
    *before* tokenisation. Bigrams need none of that and lose little here: Han
    is largely morphemic, so two adjacent characters approximate a word, and the
    handful of spurious cross-word bigrams are rare enough to be absorbed by IDF
    - a bigram straddling two words is by definition uncommon, so it carries
    almost no weight in `Retriever._lexical_score`.

    Runs of one character are kept whole. A single Han character is a word
    (`年`, `假`), unlike a single Latin letter, which is why the length filter in
    `tokenize` is applied to Latin terms only.
    """
    terms: list[str] = []
    for run in _CJK_RUN_RE.findall(text) + _HANGUL_RUN_RE.findall(text):
        if len(run) == 1:
            terms.append(run)
            continue
        terms.extend(run[i : i + 2] for i in range(len(run) - 1))
    return terms
