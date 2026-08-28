"""The Zenith portal page: five locales, two themes, one document.

The page is served as a single string, so nothing about it fails loudly. A
locale missing a key renders an English sentence in a Japanese UI; a theme
missing a custom property renders black text on a near-black background. Both
are invisible to every other test in this suite, which is why these exist.
"""

from __future__ import annotations

import json
import re

import pytest

from src.ui.portal import (
    CHAT_UI_HTML,
    SUPPORTED_LOCALES,
    TRANSLATIONS,
    render_page,
)

BADGE = '<span class="badge build-badge">test</span>'

#: Keys whose value is a proper noun or an acronym and is legitimately the
#: same in every locale. Everything else differing from English is the signal
#: that a locale was actually translated.
SHARED_VERBATIM = {"login_email_ph"}


@pytest.fixture(scope="module")
def page() -> str:
    return render_page(BADGE)


def _keys(locale: str) -> set[str]:
    return set(TRANSLATIONS[locale])


# --- the locale table ---------------------------------------------------------


def test_every_advertised_locale_has_a_table():
    """`SUPPORTED_LOCALES` is what the rest of the app reads; it cannot lie."""
    assert set(SUPPORTED_LOCALES) == set(TRANSLATIONS)


def test_english_is_present_because_everything_falls_back_to_it():
    assert "en-US" in TRANSLATIONS
    assert TRANSLATIONS["en-US"]


@pytest.mark.parametrize("locale", [loc for loc in SUPPORTED_LOCALES if loc != "en-US"])
def test_a_locale_translates_every_key_english_defines(locale):
    """A missing key is not a crash - it is an English sentence mid-paragraph."""
    missing = _keys("en-US") - _keys(locale)

    assert not missing, f"{locale} is missing: {sorted(missing)}"


@pytest.mark.parametrize("locale", [loc for loc in SUPPORTED_LOCALES if loc != "en-US"])
def test_a_locale_defines_nothing_english_does_not(locale):
    """A key only one locale has is a key nothing reads - almost always a typo."""
    orphans = _keys(locale) - _keys("en-US")

    assert not orphans, f"{locale} has keys absent from en-US: {sorted(orphans)}"


@pytest.mark.parametrize("locale", SUPPORTED_LOCALES)
def test_no_translation_is_blank(locale):
    blank = [k for k, v in TRANSLATIONS[locale].items() if not v.strip()]

    assert not blank, f"{locale} has empty strings for: {sorted(blank)}"


@pytest.mark.parametrize("locale", [loc for loc in SUPPORTED_LOCALES if loc != "en-US"])
def test_a_locale_is_actually_translated_and_not_a_copy_of_english(locale):
    """Guards the failure where a locale is added by pasting the English block."""
    english = TRANSLATIONS["en-US"]
    same = [
        k for k, v in TRANSLATIONS[locale].items()
        if v == english[k] and k not in SHARED_VERBATIM
    ]

    # Acronyms and product names ("Dev", "Token", "FastMCP") legitimately
    # survive translation, so this is a ceiling rather than a demand for zero.
    assert len(same) < len(english) * 0.25, f"{locale} looks untranslated: {sorted(same)[:12]}"


@pytest.mark.parametrize("locale", SUPPORTED_LOCALES)
def test_interpolation_placeholders_survive_translation(locale):
    """`{name}` and `{id}` are substituted at runtime.

    A translator who renders `{id}` as `{識別子}` produces a sentence with a
    literal brace in it and no employee number, which reads as a bug in the
    agent rather than in the copy.
    """
    english = TRANSLATIONS["en-US"]
    for key, source in english.items():
        expected = set(re.findall(r"\{(\w+)\}", source))
        actual = set(re.findall(r"\{(\w+)\}", TRANSLATIONS[locale][key]))

        assert expected == actual, f"{locale}.{key}: expected {expected}, got {actual}"


# --- what the markup asks for -------------------------------------------------


def _markup_keys(attr: str) -> set[str]:
    return set(re.findall(rf'{attr}="([^"]+)"', CHAT_UI_HTML))


@pytest.mark.parametrize("attr", ["data-i18n", "data-i18n-placeholder", "data-i18n-title"])
def test_every_key_the_markup_requests_exists(attr):
    """The page renders `t(key)`, which falls back to printing the key itself."""
    unknown = _markup_keys(attr) - _keys("en-US")

    assert not unknown, f"{attr} references undefined keys: {sorted(unknown)}"


def test_every_quick_action_has_a_label_a_description_and_a_prompt():
    """Each `ACTIONS` entry expands into three keys; a missing one is silent."""
    stems = re.findall(r"k: '(a_\w+)'", CHAT_UI_HTML)

    assert stems, "no quick actions found - has the ACTIONS array been renamed?"
    for stem in stems:
        for suffix in ("_l", "_d", "_p"):
            assert stem + suffix in TRANSLATIONS["en-US"], f"missing {stem}{suffix}"


def test_every_nav_category_has_a_label():
    keys = re.findall(r"key: '(nav_\w+)'", CHAT_UI_HTML)

    assert keys
    assert not set(keys) - _keys("en-US")


def test_the_language_menu_offers_exactly_the_supported_locales(page):
    offered = re.findall(r'<option value="([^"]+)"', page)

    assert set(offered) == set(SUPPORTED_LOCALES)


# --- the two themes -----------------------------------------------------------


def _custom_properties(selector: str) -> set[str]:
    block = re.search(rf"{re.escape(selector)} \{{(.*?)\n    \}}", CHAT_UI_HTML, re.S)
    assert block, f"no {selector} block found"
    return set(re.findall(r"(--[\w-]+):", block.group(1)))


def test_dark_mode_overrides_every_colour_light_mode_defines():
    """An unoverridden property keeps its washi-paper value on an ink page -
    which is how you get near-white text on near-white background."""
    light = _custom_properties(":root")
    dark = _custom_properties("html.dark")

    assert light == dark, f"only in light: {light - dark}; only in dark: {dark - light}"


def test_the_theme_is_resolved_before_first_paint(page):
    """Reading the stored theme on DOMContentLoaded makes dark mode flash white."""
    head = page.split("</head>")[0]

    assert "zenith_theme" in head
    assert "prefers-color-scheme" in head


def test_reduced_motion_disables_the_theme_transition(page):
    assert "prefers-reduced-motion" in page


# --- the rendered document ----------------------------------------------------


def test_the_page_is_a_complete_document(page):
    assert page.startswith("<!DOCTYPE html>")
    assert page.rstrip().endswith("</html>")


def test_no_placeholder_survives_rendering(page):
    assert "__I18N__" not in page
    assert "__BUILD_BADGE__" not in page


def test_the_build_badge_is_substituted_where_the_header_expects_it(page):
    assert BADGE in page


def test_the_whole_translation_table_reaches_the_browser(page):
    """Injected as JSON rather than written into the script, so that the table
    above is the single source of truth the tests can reach."""
    payload = re.search(r"const I18N = (\{.*?\});\n", page, re.S)
    assert payload, "the I18N assignment is no longer recognisable"

    shipped = json.loads(payload.group(1))

    assert shipped == TRANSLATIONS


def test_injected_copy_cannot_close_the_script_block():
    """A translation containing `</script>` would end the block early and spill
    the rest of the page into the document as text."""
    hostile = {"en-US": {"welcome": "</script><img src=x onerror=alert(1)>"}}
    original = dict(TRANSLATIONS)
    try:
        TRANSLATIONS.clear()
        TRANSLATIONS.update(hostile)
        rendered = render_page(BADGE)
    finally:
        TRANSLATIONS.clear()
        TRANSLATIONS.update(original)

    script_body = rendered.split("const I18N = ")[1].split(";\n")[0]

    assert "</script>" not in script_body
    assert "\\u003c" in script_body


def test_the_agent_reply_is_inserted_as_text_not_markup():
    """Model output carrying a re-identified phone number is not markup, and
    treating it as markup is how it becomes an injection."""
    assert "bubble.textContent = text;" in CHAT_UI_HTML
    assert "bubble.innerHTML = text" not in CHAT_UI_HTML


# --- behaviour the restyle had to preserve ------------------------------------


@pytest.mark.parametrize(
    "handler",
    [
        "openLoginModal()",
        "closeLoginModal()",
        "handleConnect()",
        "openTokenModal()",
        "closeTokenModal()",
        "handleUpdateToken()",
        "toggleTokenVis()",
        "toggleTokenUpdateVis()",
        "logout()",
        "sendMessage()",
        "handleRegistryToggle(this.checked)",
    ],
)
def test_the_restyle_kept_every_control_the_old_page_had(handler):
    """This was a restyle, not a rewrite. Losing a handler loses a feature."""
    assert handler in CHAT_UI_HTML


@pytest.mark.parametrize(
    "element_id",
    [
        "loginModal", "tokenModal", "loginEmail", "loginToken", "tokenUpdateInput",
        "userInput", "chatWindow", "typingIndicator", "registryToggle",
        "registryBadge", "userDisplayName", "userEmailSpan", "userEmpBadge",
        "langSelect", "themeIcon",
    ],
)
def test_the_elements_the_script_reaches_for_exist(element_id):
    assert f'id="{element_id}"' in CHAT_UI_HTML


@pytest.mark.parametrize(
    "endpoint", ["/chat", "/auth/me", "/auth/quick-login", "/auth/update-mcp-token"]
)
def test_the_page_still_calls_every_backend_endpoint(endpoint):
    assert f"'{endpoint}'" in CHAT_UI_HTML
