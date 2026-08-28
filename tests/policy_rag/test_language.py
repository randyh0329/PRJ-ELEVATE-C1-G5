"""Script detection and CJK bigramming.

The interesting cases are all *ambiguity*, so the tests are organised by what
makes each one ambiguous rather than by language. Japanese and Chinese share
most of their characters; a terse query may contain no distinguishing character
at all; and Korean is the only one of the three a single regex settles.

What is deliberately *not* asserted is that detection is always right. It cannot
be - `年次有給休暇` and its Chinese reading are the same string - and the design
answer is that the ambiguity is confined to the answer language, because
retrieval runs off the embedding and never calls `detect`. The tests below pin
which way each unresolvable case falls, so that a future change to the tie-break
is a decision rather than an accident.
"""

from __future__ import annotations

import pytest

from src.grounding.policy_rag.language import (
    AMBIGUOUS_HAN_DEFAULT,
    CORPUS_LANGUAGE,
    ENGLISH,
    JAPANESE,
    KOREAN,
    SIMPLIFIED_CHINESE,
    TRADITIONAL_CHINESE,
    cjk_terms,
    detect,
    resolve,
)

# --- the unambiguous cases ----------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "How many days of bereavement leave do I get?",
        "",
        "   ",
        "EMP-1001",
        "2026-08-27",
    ],
)
def test_latin_text_is_the_corpus_language_and_not_cross_lingual(text):
    language = detect(text)

    assert language.code == ENGLISH == CORPUS_LANGUAGE
    assert language.cross_lingual is False


@pytest.mark.parametrize(
    "text",
    [
        "연차 휴가는 며칠인가요?",
        "병가",
        # Jamo rather than composed syllables - the same language, and a form
        # an IME emits mid-composition.
        "ㅎㅕㅇ",
    ],
)
def test_any_hangul_at_all_makes_it_korean(text):
    """Hangul is used by exactly one language, so no evidence-weighing applies."""
    assert detect(text).code == KOREAN


def test_kana_settles_japanese_even_when_most_of_the_query_is_kanji():
    assert detect("有給休暇は何日ありますか").code == JAPANESE
    assert detect("ハラスメント").code == JAPANESE


# --- Japanese against Chinese, where the scripts overlap ----------------------


def test_a_kanji_japan_simplified_alone_is_positive_evidence_of_japanese():
    """`図` and `経` exist in neither Chinese orthography. A terse all-kanji
    query has no kana to give it away, so these carry the decision."""
    assert detect("組織図").code == JAPANESE
    assert detect("経済").code == JAPANESE


def test_a_shared_kanji_compound_only_japan_forms_is_read_as_japanese():
    """Every character in `契約社員` is shared, so character inspection alone
    reads it as Chinese. The word is one of the most common things an employee
    of an HR system types, which is what makes the shortlist worth its cost."""
    assert detect("契約社員").code == JAPANESE
    assert detect("年次有給休暇").code == JAPANESE


def test_japanese_is_ruled_out_before_the_chinese_orthographies_are_weighed():
    """Japanese shinjitai overlaps heavily with the Traditional column, so this
    order is load-bearing: reversed, every kana-free Japanese query would be
    reported as Chinese."""
    assert detect("勤務時間").code == JAPANESE


# --- Traditional against Simplified -------------------------------------------


def test_simplified_only_characters_win_the_census():
    assert detect("我们的病假政策是什么").code == SIMPLIFIED_CHINESE


def test_traditional_only_characters_win_the_census():
    assert detect("請問特休假的規定為何").code == TRADITIONAL_CHINESE


def test_han_with_no_orthography_evidence_falls_to_the_documented_default():
    """`婚假` is spelled identically in both. Nothing can separate them, so the
    tie-break is a stated choice - the Taiwan office - not a coin flip."""
    language = detect("婚假")

    assert language.code == AMBIGUOUS_HAN_DEFAULT == TRADITIONAL_CHINESE
    assert language.cross_lingual is True


# --- the explicit override ----------------------------------------------------


@pytest.mark.parametrize("code", [JAPANESE, KOREAN, TRADITIONAL_CHINESE, SIMPLIFIED_CHINESE])
def test_a_supported_request_beats_detection(code):
    """A browser `Accept-Language` beats any amount of character counting on a
    two-word query, so a caller that knows its user's locale gets to say so."""
    language = resolve("bereavement leave", requested=code)

    assert language.code == code
    assert language.cross_lingual is True


def test_requesting_the_corpus_language_is_not_cross_lingual():
    assert resolve("休暇", requested=ENGLISH).cross_lingual is False


@pytest.mark.parametrize("requested", [None, "", "klingon", "ja-JP", "EN"])
def test_an_unrecognised_request_falls_back_to_detection_rather_than_erroring(requested):
    """The parameter is a hint about presentation. Refusing a policy question
    over a malformed locale tag would be a poor trade - and note `ja-JP` and
    `EN`: near-misses are ignored rather than guessed at, because guessing here
    means answering in a language the user did not ask for."""
    assert resolve("有給休暇", requested=requested).code == JAPANESE


def test_an_empty_query_honours_the_caller_supplied_default():
    assert detect("", default=KOREAN).code == KOREAN
    assert detect("", default=KOREAN).cross_lingual is True


def test_a_language_renders_as_its_code():
    """It ends up interpolated into log lines and prompt text."""
    assert f"{detect('휴가')}" == KOREAN


# --- bigramming ---------------------------------------------------------------


def test_a_cjk_run_becomes_overlapping_character_bigrams():
    assert cjk_terms("年次有給") == ["年次", "次有", "有給"]


def test_han_and_kana_are_bigrammed_across_the_script_boundary():
    """Japanese interleaves the two inside one word, so splitting on the script
    boundary would cut exactly the compounds worth matching."""
    assert "い合" in cjk_terms("お問い合わせ")


def test_a_lone_cjk_character_is_kept_whole():
    """A single Han character is a word - unlike a single Latin letter, which is
    why `tokenize` applies its length filter to Latin terms only."""
    assert cjk_terms("年") == ["年"]


def test_hangul_runs_are_bigrammed_too():
    assert cjk_terms("연차휴가") == ["연차", "차휴", "휴가"]


def test_latin_text_yields_no_cjk_terms():
    """`tokenize` still handles Latin; this must not double-count it."""
    assert cjk_terms("bereavement leave policy 2026") == []


def test_runs_are_split_on_the_punctuation_and_spaces_between_them():
    assert cjk_terms("年次、有給") == ["年次", "有給"]
