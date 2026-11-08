import os
import re

from infinifind_music import i18n, paths


def test_normalize_accepts_variants_and_defaults_to_english():
    assert i18n.normalize("pt") == "pt-BR"
    assert i18n.normalize("PT-br") == "pt-BR"
    assert i18n.normalize("es-MX") == "es"
    assert i18n.normalize("fr") == "en-US"
    assert i18n.normalize(None) == "en-US"


def test_every_language_has_every_message():
    english = set(i18n.MESSAGES["en-US"])
    for lang in i18n.LANGUAGES:
        assert set(i18n.MESSAGES[lang]) == english, lang


def test_format_and_price():
    assert i18n.t("pt-BR", "songs", n=3) == "3 músicas"
    assert i18n.price("en-US", "USD", 1.29) == "USD 1.29"
    assert i18n.price("pt-BR", "BRL", 2.9) == "BRL 2,90"


def ui_strings():
    """Keys of each language block in the STRINGS object of ui.html."""
    with open(os.path.join(paths.WEB_DIR, "ui.html"), encoding="utf-8") as f:
        page = f.read()
    block = page.split("const STRINGS = {", 1)[1].split("\n};", 1)[0]
    parts = re.split(r'^  "([a-zA-Z-]+)": \{$', block, flags=re.M)[1:]
    keys = {
        lang: set(re.findall(r"^    (\w+):", body, flags=re.M))
        for lang, body in zip(parts[::2], parts[1::2])
    }
    used = set(re.findall(r'data-i18n(?:-placeholder|-aria|-title)?="(\w+)"', page))
    return keys, used


def test_interface_translations_are_complete():
    keys, used = ui_strings()
    assert set(keys) == {"en-US", "pt-BR", "es"}
    for lang, lang_keys in keys.items():
        assert lang_keys == keys["en-US"], lang
    assert used <= keys["en-US"]
