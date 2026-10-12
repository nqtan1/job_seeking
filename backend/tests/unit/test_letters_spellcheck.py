"""The model proposes corrections; code keeps only what truly applies to the text."""

from recruitai.modules.letters.schemas import RawSpellIssue, SpellItem
from recruitai.modules.letters.spellcheck import MAX_ISSUES, validate


def item(key: str, text: str) -> SpellItem:
    return SpellItem(key=key, text=text)


def raw(
    key: str, wrong: str, right: str, reason: str = "accord", context: str = ""
) -> RawSpellIssue:
    return RawSpellIssue(
        key=key, wrong=wrong, right=right, reason=reason, context=context
    )


def test_a_real_error_gets_exact_offsets_and_nothing_else_is_kept():
    text = "Je suis très motivé par cette opportunitée unique."
    items = [item("opening", text)]
    got = validate(
        items,
        [
            raw("opening", "opportunitée", "opportunité"),
            raw("opening", "poste de rêve", "poste idéal"),  # not in the text: dropped
            raw("body.9", "x", "y"),  # unknown paragraph: dropped
            raw("opening", "unique", "unique"),  # no change: dropped
        ],
    )
    assert len(got) == 1
    issue = got[0]
    assert (
        text[issue.start : issue.end] == "opportunitée" and issue.right == "opportunité"
    )


def test_a_fragment_inside_a_longer_word_is_never_matched():
    # "a" must not be found inside "table"/"chat"; only the standalone word is an error.
    text = "Le chat a mangé sur la table."
    got = validate(
        [item("body.0", text)], [raw("body.0", "a", "à")]
    )  # the only standalone "a"
    assert [(i.start, i.end) for i in got] == [(8, 9)]
    assert text[8:9] == "a"


def test_repeated_errors_each_get_their_own_occurrence_in_order():
    text = "Il à dit que il à fini."
    got = validate(
        [item("body.0", text)],
        [
            raw("body.0", "à", "a", context="Il à dit que"),
            raw("body.0", "à", "a", context="que il à fini."),
        ],
    )
    assert [i.start for i in got] == [3, 16]
    assert all(text[i.start : i.end] == "à" for i in got)


def test_a_rewrite_disguised_as_a_correction_is_dropped():
    text = "Je travaille depuis cinq ans dans le developement logiciel."
    sentence = (
        "Depuis cinq années, j'exerce avec passion dans le génie logiciel moderne"
    )
    got = validate(
        [item("opening", text)],
        [
            raw("opening", text[:-1], sentence),  # whole-sentence rewrite
            raw("opening", "developement", "développement"),  # a real fix
        ],
    )
    assert [i.right for i in got] == ["développement"]


def test_results_follow_the_reading_order_and_overlaps_keep_the_first():
    items = [
        item("body.0", "un exemple faut"),
        item("opening", "bonjour tout le monde"),
    ]
    got = validate(
        items,
        [
            raw("opening", "tout le monde", "tout-le-monde"),
            raw("body.0", "exemple faut", "exemple faux"),
            raw("body.0", "faut", "faux"),  # overlaps the previous one
        ],
    )
    assert [(i.key, i.wrong) for i in got] == [
        ("body.0", "exemple faut"),
        ("opening", "tout le monde"),
    ]


def test_reason_is_trimmed_and_the_list_is_capped():
    words = [f"{chr(97 + n // 26)}{chr(97 + n % 26)}x" for n in range(MAX_ISSUES + 10)]
    got = validate(
        [item("body.0", " ".join(words))],
        [raw("body.0", w, w + "s", reason="x" * 500) for w in words],
    )
    assert len(got) == MAX_ISSUES and len(got[0].reason) <= 160


def test_a_repeated_word_is_located_by_its_context_never_guessed():
    # Only the LAST "a" is wrong; the first one is correct and must not be touched.
    text = "Il a un chat. Il a mangé à midi. Je vais a Paris"
    items = [item("body.0", text)]
    [issue] = validate(items, [raw("body.0", "a", "à", context="Je vais a Paris")])
    assert text[issue.start : issue.end] == "a" and issue.start == text.rindex(
        "a Paris"
    )
    # No context and several candidates: dropped, because a wrong guess "fixes" a correct word.
    assert validate(items, [raw("body.0", "a", "à")]) == []
    # A unique occurrence needs no context.
    assert len(validate(items, [raw("body.0", "mangé", "mange")])) == 1


def test_typography_the_model_normalises_away_still_matches_the_original_text():
    nnbsp = "\u202f"
    cases = [
        (
            "L\u2019opportunite est rare",
            "L'opportunite",
            "L'opportunité",
        ),  # curly apostrophe
        (
            f"Bonjour{nnbsp}: une erreur eror ici",
            "eror",
            "erreur",
        ),  # French narrow NBSP
        ("Je suis passione\u0301 par ça", "passioné", "passionné"),  # NFD accent
        ("pro\u200bbleme grave", "probleme", "problème"),  # zero-width space inside
    ]
    for text, wrong, right in cases:
        got = validate([item("opening", text)], [raw("opening", wrong, right)])
        assert len(got) == 1, text
        # The span handed to the client is the ORIGINAL text, so its equality check holds.
        assert text[got[0].start : got[0].end] == got[0].wrong


def test_offsets_are_utf16_code_units_like_javascript_strings():
    text = "🚀 Je suis motivé et j'ai une erreur: eror"
    [issue] = validate([item("body.0", text)], [raw("body.0", "eror", "erreur")])
    utf16 = text.encode("utf-16-le")
    assert utf16[issue.start * 2 : issue.end * 2].decode("utf-16-le") == "eror"
    assert issue.start == text.index("eror") + 1  # one astral char before the span


def test_model_output_is_cleaned_before_use():
    text = "Je suis passioné par les données."
    items = [item("opening", text)]
    # HTML entities (seen from the real model) are decoded, not silently lost.
    [fixed] = validate(items, [raw("opening", "passioné", "passionn&eacute;")])
    assert fixed.right == "passionné"
    # A correction may not smuggle in an invisible/non-breaking character (seen: "passion\xa0é").
    assert validate(items, [raw("opening", "passioné", "passion\u00a0é")]) == []
    assert (
        validate(items, [raw("opening", "passioné", "passionné\u200e")])[0].right
        == "passionné"
    )


def test_short_rewrites_and_changed_numbers_are_not_corrections():
    text = "Je maîtrise Java depuis 2019 et Paris me plaît."
    items = [item("body.0", text)]
    for wrong, right in [("Java", "Rust"), ("2019", "2024"), ("Paris", "Lyon")]:
        assert validate(items, [raw("body.0", wrong, right)]) == []
    # ... while genuine short fixes still pass: homophones, accents-only, capitalisation.
    for text2, wrong, right in [
        ("Je vais a Paris", "a", "à"),
        ("Ca va bien", "Ca", "Ça"),
        ("il habite à paris", "paris", "Paris"),
        ("Ils ont fini", "ont", "sont"),
    ]:
        assert validate([item("body.0", text2)], [raw("body.0", wrong, right)]), text2
