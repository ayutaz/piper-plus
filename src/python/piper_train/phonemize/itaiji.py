"""Variant kanji (異体字) normalization for Japanese text preprocessing.

This module normalizes variant kanji characters to their standard forms using
dictionaries from the CJKV Ideograph Database.

Dictionaries used:
- jinmei-variants.txt: Ministry of Justice personal name kanji variants
- joyo-variants.txt: Ministry of Education standard kanji variants
- non-cjk.txt: Non-CJK/pseudo-kanji to kanji mappings

Original source: kabosu-core (https://github.com/q9uri/kabosu-core)
Dictionary source: CJKV Ideograph Database (https://kanji-database.sourceforge.net/)

License:
© 2009 CJKV (Chinese Japanese Korean Vietnamese) Ideograph Database
MIT License
"""

import os
from pathlib import Path


def _load_text(file_path: str) -> list[list[str]]:
    """Load dictionary text file and parse into list of mappings.

    Args:
        file_path: Path to dictionary text file

    Returns:
        List of [standard_char, unicode_code, variant_char] mappings
    """
    with open(file_path, encoding="utf8") as f:
        data = f.read().split("\n")

    # Filter and parse lines
    parsed_data = []
    for line in data:
        # Skip empty lines, comments, and metadata
        if not line or line[0] == "#" or line == "\x1a":
            continue

        # Skip metadata lines from dictionary files
        if line[:5] == "jinmei" or line[:4] == "joyo" or line[:6] == "non-cjk":
            continue

        # Skip katakana section from non-cjk.txt
        if "non-cjk/katakana" in line:
            continue

        # Parse comma-separated values
        parsed_data.append(line.split(","))

    return parsed_data


def normalize_itaiji(text: str, debug_print: bool = False) -> str:
    """Normalize variant kanji (異体字) to standard forms.

    This function replaces variant kanji characters with their standard equivalents
    using dictionaries of officially recognized variants.

    Args:
        text: Input text containing variant kanji
        debug_print: If True, print debug information about replacements

    Returns:
        Text with variant kanji normalized to standard forms

    Examples:
        >>> normalize_itaiji("齋藤")  # variant of 斎藤
        "斎藤"
        >>> normalize_itaiji("邊")  # variant of 辺
        "辺"
    """
    dir_path = Path(__file__).parent
    itaiji_list = []

    # Load variant kanji dictionaries
    dict_jinmei_path = dir_path / "dict" / "jinmei-variants.txt"
    dict_joyo_path = dir_path / "dict" / "joyo-variants.txt"
    dict_non_cjk_path = dir_path / "dict" / "non-cjk.txt"

    itaiji_list += _load_text(str(dict_jinmei_path))
    itaiji_list += _load_text(str(dict_joyo_path))
    itaiji_list += _load_text(str(dict_non_cjk_path))

    # Build list of all variant characters (column 3)
    variant_chars = [entry[2] for entry in itaiji_list]

    # Remove circular mappings (where a standard form appears as a variant elsewhere)
    # This prevents infinite replacement loops
    delete_indices = []

    for i, entry in enumerate(itaiji_list):
        standard_char = entry[0]

        # Check if this standard character appears as a variant elsewhere
        while standard_char in variant_chars:
            idx = variant_chars.index(standard_char)

            # Mark as checked to avoid re-processing
            variant_chars[idx] = "Checked"

            if debug_print:
                print(f"Circular mapping found: {itaiji_list[idx]}, index: {idx}")

            # If the circular reference appears earlier in the list,
            # it should be removed to prevent incorrect ordering
            if idx < i:
                delete_indices.append(idx)

    # Remove circular mappings (in reverse order to maintain indices)
    for idx in sorted(set(delete_indices), reverse=True):
        itaiji_list.pop(idx)

    # Perform variant replacement
    for entry in itaiji_list:
        variant_char = entry[2]
        standard_char = entry[0]

        if variant_char in text:
            text = text.replace(variant_char, standard_char)

    return text
