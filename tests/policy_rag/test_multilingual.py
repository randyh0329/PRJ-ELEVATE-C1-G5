"""The language layer, once the hardcoded list was taken out of it.

Two things are being pinned here, and they pull in opposite directions.

The first is that the limit is gone. Detection is no longer bounded by five
character tables, retrieval no longer refuses a question because it was typed in
the wrong script, and a caller may name any language that exists.

The five with tests behind them - English, Japanese, Korean, Traditional Chinese
and Indonesian - are the offices Altostrat Singapore staffs from, and Indonesian
is the one that shows why the tables had to go rather than grow. It is written
in Latin script, so no Unicode range could ever separate it from English; the
census does not fail to classify it, it classifies it *as English*, and the
employee is answered in a language they did not write in by a system that never
noticed. That is not a missing table. It is the wrong mechanism.

The second is that removing the limit must not remove the floor. Gemini is
unreachable from CI and from a laptop without credentials, and a policy service
that stops answering *English* questions because a translation endpoint is down
has been made worse, not more multilingual. So every path through this module
has a documented fallback, and most of what follows is about proving the
fallback is taken silently, correctly, and without an exception reaching a
caller who only ever asked about bereavement leave.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.grounding.policy_rag.language import ENGLISH, JAPANESE, TRADITIONAL_CHINESE, detect
from src.grounding.policy_rag.multilingual import (
    DEFAULT_MODEL,
    LanguageService,
    Understanding,
)


class FakeClient:
    """A `google.genai` client that returns canned JSON and records its calls."""

    def __init__(self, payloads: list | Exception, text: str | None = None) -> None:
        self._payloads = payloads
        self._text = text
        self.calls: list[dict] = []
        self.models = SimpleNamespace(generate_content=self._generate)

    def _generate(self, *, model, contents, config):
        self.calls.append(
            {"model": model, "contents": contents, "instruction": config.system_instruction}
        )
        if isinstance(self._payloads, Exception):
            raise self._payloads
        if self._text is not None:
            return SimpleNamespace(text=self._text)
        payload = self._payloads.pop(0) if len(self._payloads) > 1 else self._payloads[0]
        return SimpleNamespace(text=json.dumps(payload))


def service(payloads=None, text=None) -> tuple[LanguageService, FakeClient]:
    client = FakeClient(payloads if payloads is not None else [{}], text=text)
    return LanguageService(client=client), client


@pytest.fixture(autouse=True)
def language_service_on(monkeypatch):
    monkeypatch.delenv("POLICY_RAG_LANGUAGE_SERVICE", raising=False)
    monkeypatch.delenv("POLICY_RAG_LANGUAGE_MODEL", raising=False)


# --- the limit is gone --------------------------------------------------------


#: The languages this service is being held to: the offices it staffs from,
#: plus the corpus language. Gemini is not restricted to these - the whole point
#: of the change is that there is no list in the code - but these are the ones
#: with tests behind them.
SUPPORTED = {
    "en": "How many sick leave days do I have?",
    "ja": "病気休暇は何日ありますか",
    "ko": "병가는 며칠 사용할 수 있나요",
    "zh-Hant": "我有幾天病假可以請",
    "id": "Berapa hari cuti sakit yang saya miliki",
}


@pytest.mark.parametrize(("tag", "query"), sorted(SUPPORTED.items()))
def test_each_supported_language_is_read_as_itself(tag, query):
    svc, _ = service([{"language": tag, "english_query": "how many sick leave days do I have"}])

    reading = svc.understand(query)

    assert reading.language.code == tag
    assert reading.language.cross_lingual is (tag != "en")
    assert reading.source == "gemini"


def test_indonesian_is_the_case_the_script_census_cannot_reach():
    """Latin script, so there is no Unicode range that could ever separate it.

    `detect` reports Indonesian as *English* - not as unknown, as English - and
    the employee gets an English answer to a question the system never realised
    it had failed to read. Japanese, Korean and Chinese were at least visible to
    a character census; adding Indonesian to it is not possible in principle,
    which is why the reading had to move to a model rather than grow a sixth
    table.
    """
    query = SUPPORTED["id"]
    assert detect(query).code == ENGLISH  # the floor genuinely cannot see it

    svc, _ = service([{"language": "id", "english_query": "how many sick leave days do I have"}])

    assert svc.understand(query).language.code == "id"


def test_the_query_is_rendered_into_english_for_retrieval():
    """The half that makes non-English *work* rather than merely be detected.

    The index is embedded with `bge-small-en-v1.5`. A Chinese question embedded
    verbatim lands nowhere near the Chinese-free chunk that answers it, which is
    why 給我請病假的規則細節 came back as a flat refusal against an index that
    contained the answer.
    """
    svc, _ = service([{"language": "zh-Hant", "english_query": "sick leave rules"}])

    reading = svc.understand("給我請病假的規則細節")

    assert reading.search_text == "sick leave rules"
    assert reading.translated is True


def test_an_english_question_is_not_round_tripped():
    svc, _ = service([{"language": "en", "english_query": "how much bereavement leave"}])

    reading = svc.understand("how much bereavement leave")

    assert reading.language.cross_lingual is False
    assert reading.translated is False


def test_a_caller_supplied_locale_governs_the_answer_language():
    """The model reads the question; the caller owns who is reading the answer.

    An employee may type a question in English and still want the answer in
    Indonesian. Detection cannot know that and must not overrule it.
    """
    svc, _ = service([{"language": "en", "english_query": "annual leave entitlement"}])

    reading = svc.understand("annual leave entitlement", requested="id")

    assert reading.language.code == "id"
    assert reading.search_text == "annual leave entitlement"


def test_the_model_used_is_the_one_the_rest_of_the_system_routes_on():
    svc, client = service([{"language": "ja", "english_query": "sick leave"}])

    svc.understand("病気休暇")

    assert client.calls[0]["model"] == DEFAULT_MODEL == "gemini-3.7-flash"


def test_the_model_is_overridable_without_a_code_change(monkeypatch):
    monkeypatch.setenv("POLICY_RAG_LANGUAGE_MODEL", "gemini-3.1-pro")
    client = FakeClient([{"language": "ja", "english_query": "sick leave"}])
    svc = LanguageService(client=client)

    svc.understand("病気休暇")

    assert client.calls[0]["model"] == "gemini-3.1-pro"


# --- the floor is still there -------------------------------------------------


def test_an_unreachable_model_falls_back_to_the_script_census():
    """NFR-4.1. The service that existed before this module still has to work."""
    svc, _ = service(RuntimeError("503 Service Unavailable"))

    reading = svc.understand("有給休暇について教えてください")

    assert reading.language.code == JAPANESE
    assert reading.source == "heuristic"
    assert reading.translated is False


def test_unparseable_output_is_treated_as_no_answer_not_as_an_answer():
    """A model that returns prose where JSON was asked for has told us nothing.

    The failure mode this forecloses is worse than a refusal: `search_text` set
    to a sentence of apology, retrieved against, and cited.
    """
    svc, _ = service(text="I'm sorry, I can't help with that.")

    reading = svc.understand("給我請病假的規則細節")

    assert reading.source == "heuristic"
    assert reading.search_text == "給我請病假的規則細節"


def test_a_response_missing_the_language_key_falls_back():
    svc, _ = service([{"english_query": "sick leave"}])

    assert svc.understand("病假").source == "heuristic"


def test_a_fenced_json_block_is_still_read():
    """Common enough deviation to strip rather than fail on."""
    svc, _ = service(text='```json\n{"language": "ko", "english_query": "sick leave"}\n```')

    reading = svc.understand("병가")

    assert reading.language.code == "ko"
    assert reading.search_text == "sick leave"


def test_an_empty_english_rendering_never_replaces_the_query():
    """Searching on an empty string matches nothing and refuses everything."""
    svc, _ = service([{"language": "zh-Hant", "english_query": ""}])

    assert svc.understand("病假").search_text == "病假"


def test_an_empty_query_never_reaches_the_model():
    svc, client = service([{"language": "en", "english_query": ""}])

    reading = svc.understand("   ")

    assert client.calls == []
    assert reading.source == "heuristic"


def test_the_service_can_be_pinned_off_for_a_reproducible_evaluation(monkeypatch):
    """A golden set must not move because a model revision shipped."""
    monkeypatch.setenv("POLICY_RAG_LANGUAGE_SERVICE", "off")
    client = FakeClient([{"language": "id", "english_query": "sick leave"}])
    svc = LanguageService(client=client)

    reading = svc.understand(SUPPORTED["id"])

    assert client.calls == []
    assert reading.source == "heuristic"


def test_a_missing_genai_package_does_not_raise_on_import_or_on_use(monkeypatch):
    """No credentials on this box is the normal case, not an error case."""
    svc = LanguageService()
    monkeypatch.setattr(svc, "_get_client", lambda: None)

    assert svc.understand("病假").source == "heuristic"
    assert svc.localize("Please note", TRADITIONAL_CHINESE) == "Please note"


# --- caching ------------------------------------------------------------------


def test_a_repeated_query_is_not_re_translated():
    """This sits on the critical path of every policy question."""
    svc, client = service([{"language": "zh-Hant", "english_query": "sick leave"}])

    for _ in range(4):
        svc.understand("給我請病假的規則細節")

    assert len(client.calls) == 1


def test_the_same_text_in_two_requested_languages_is_cached_separately():
    svc, client = service([{"language": "en", "english_query": "leave policy"}])

    svc.understand("leave policy", requested="ko")
    svc.understand("leave policy", requested="id")

    assert len(client.calls) == 2


# --- localisation of the fixed strings ----------------------------------------


def test_a_refusal_goes_out_in_the_employees_language():
    """The response they are most likely to get when something has gone wrong.

    A refusal an employee cannot read is indistinguishable from a broken
    service, and it is precisely the message that has to be understood: it is
    the one telling them to go and ask a human instead.
    """
    svc, client = service([{"text": "我在員工手冊中找不到這項政策。"}])

    out = svc.localize("I could not find that in the handbook.", TRADITIONAL_CHINESE)

    assert out == "我在員工手冊中找不到這項政策。"
    assert "Target language: zh-Hant" in client.calls[0]["contents"]


def test_english_is_never_sent_to_the_translator():
    svc, client = service([{"text": "should not be used"}])

    assert svc.localize("Please note", "en") == "Please note"
    assert svc.localize("Please note", "en-SG") == "Please note"
    assert client.calls == []


def test_a_failed_translation_returns_the_english_rather_than_nothing():
    """Silence is the one unacceptable outcome: the employee gets no answer at all."""
    svc, _ = service(RuntimeError("deadline exceeded"))

    assert svc.localize("Please note", "ja") == "Please note"


def test_an_empty_translation_returns_the_english():
    svc, _ = service([{"text": "   "}])

    assert svc.localize("Sources", "ko") == "Sources"


def test_a_repeated_fixed_string_is_translated_once_per_language():
    """`Sources` and `Please note` appear on every answer; they are not paid for
    on every answer."""
    svc, client = service([{"text": "出典"}])

    for _ in range(5):
        svc.localize("Sources", "ja")

    assert len(client.calls) == 1


# --- what gets reported -------------------------------------------------------


def test_a_degraded_reading_is_distinguishable_from_a_confident_one():
    """`answered in English because detection failed` and `answered in English
    because the question was English` are different events to an auditor, and
    from the answer alone they look identical."""
    reachable, _ = service([{"language": "id", "english_query": "sick leave"}])
    unreachable, _ = service(RuntimeError("503"))

    assert reachable.understand(SUPPORTED["id"]).source == "gemini"
    assert unreachable.understand(SUPPORTED["id"]).source == "heuristic"


def test_translated_compares_against_what_the_employee_typed():
    typed = "給我請病假的規則細節"

    assert Understanding(
        language=TRADITIONAL_CHINESE, search_text=typed, source="heuristic", query_text=typed
    ).translated is False
    assert Understanding(
        language=TRADITIONAL_CHINESE, search_text="sick leave", source="gemini", query_text=typed
    ).translated is True
