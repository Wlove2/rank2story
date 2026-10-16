"""Independent, conservative text decoder for public ranking text.

No third-party FanqieRankTracker code or font mapping is included.

Ordinary Unicode text is already decoded by the browser and needs no replacement.
If a ranking field contains Private Use Area glyphs associated with unknown
custom fonts, reject it instead of inventing titles, authors, readership counts.
Operators who have a lawfully obtained alternate decoder may supply their own
module through NOVEL_FANQIE_COLLECTOR or --legacy-script.
"""
from __future__ import annotations

import unicodedata


def decode_text(value: object) -> str:
    """Return Unicode text only when every codepoint is verifiable as standard text.

    This deliberately does not attempt to infer proprietary, font-specific PUA
    mappings. Such mappings are not universal and decoding them incorrectly
    would fabricate source evidence.
    """
    text = str(value or "")
    for character in text:
        point = ord(character)
        if (point == 0xFFFD or
            0xE000 <= point <= 0xF8FF or
            0xF0000 <= point <= 0xFFFFD or
            0x100000 <= point <= 0x10FFFD or
            unicodedata.category(character) == "Co"):
            raise ValueError(
                f"Undecoded custom-font character U+{point:04X}; "
                "provide a rights-cleared, verified decoder for this source"
            )
    return text
