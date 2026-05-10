"""Adversarial tests for piper_plus_g2p.ssml — XXE / billion-laughs / DTD / PI.

These tests pin the *current* defensive behaviour of :class:`SSMLParser`
against well-known XML attack vectors. The cases mirror analogous
fixtures in Rust / C# / Go runtimes so cross-runtime drift can be
detected.

The contract for each case is:

1. The parser MUST NOT crash, panic, segfault, OOM, or hang.
2. The parser MUST NOT expand external entities (`file://`, `http://`, ...).
3. Either the input is rejected by ``is_ssml()`` (DOCTYPE / XML prolog
   precedes ``<speak>``) and returned as a single plain-text segment,
   OR the XML parser raises ``ET.ParseError`` and the implementation
   falls back to stripped plain text. In both branches no entity
   reference value leaks into the output.
4. For oversized inputs (> ``_MAX_SSML_SIZE``) the parser MUST raise
   ``ValueError`` to mirror the existing ``oversized_ssml_raises`` test.

The defence-in-depth here is the ``is_ssml`` regex
(``^\\s*<speak[\\s>]``) which forces ``<speak`` to be the first non-whitespace
token. Any payload that prefixes a DOCTYPE / xml prolog / processing
instruction trips the regex and bypasses XML parsing entirely. Tests
below cover both that path and the residual ``<speak>``-first path that
*does* reach :func:`xml.etree.ElementTree.fromstring`.
"""

from __future__ import annotations

import pytest

from piper_plus_g2p.ssml import _MAX_SSML_SIZE, SSMLParser


def _all_text(segments) -> str:
    """Concatenate all segment text for searching."""
    return " ".join(s.text for s in segments)


# =====================================================================
# XXE — external entity attack
# =====================================================================


class TestXxeExternalEntityBlocked:
    """``<!ENTITY xxe SYSTEM "file:///etc/passwd">`` must not resolve.

    ``xml.etree.ElementTree`` does not fetch SYSTEM entities by design,
    but we additionally require that the entity *name* (``&xxe;``) does
    not appear expanded to file contents in any segment. The most common
    code path is the ``is_ssml`` regex rejecting the DOCTYPE-prefixed
    input outright; the residual path (``<speak>`` first, undeclared
    ``&xxe;``) raises ``ET.ParseError`` and falls back to stripped text.
    """

    def test_xxe_external_entity_blocked(self):
        # Standard XXE payload — DOCTYPE precedes <speak>.
        payload = (
            '<?xml version="1.0"?>'
            '<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
            "<speak>&xxe;</speak>"
        )
        # Must not crash / hang / OOM. Sane fallback.
        segments = SSMLParser.parse(payload)
        assert len(segments) >= 1
        full_text = _all_text(segments)
        # Critical: no /etc/passwd content. The literal entity name may
        # appear in the plain-text fallback; that is acceptable.
        assert "root:" not in full_text  # /etc/passwd content marker
        assert "/bin/bash" not in full_text
        assert "/bin/sh" not in full_text

    def test_xxe_doctype_only_no_xml_prolog(self):
        # DOCTYPE without xml prolog -- still bypassed by is_ssml regex.
        payload = (
            '<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
            "<speak>&xxe;</speak>"
        )
        segments = SSMLParser.parse(payload)
        assert len(segments) >= 1
        full_text = _all_text(segments)
        assert "root:" not in full_text

    def test_xxe_speak_first_undeclared_entity(self):
        """``<speak>`` first with an undeclared entity reference.

        This bypasses the ``is_ssml`` regex guard and reaches
        :func:`ET.fromstring`, which raises ``ParseError`` for the
        undeclared entity. The implementation falls back to stripped
        plain text. The literal ``&xxe;`` token is allowed in output
        (it is a literal string, not an expanded file).
        """
        payload = "<speak>&xxe;</speak>"
        segments = SSMLParser.parse(payload)
        assert len(segments) >= 1
        full_text = _all_text(segments)
        # No file content leaked.
        assert "root:" not in full_text
        assert "/etc/passwd" not in full_text


# =====================================================================
# Billion laughs — exponential entity expansion DoS
# =====================================================================


class TestBillionLaughsBounded:
    """A 9-deep, fan-out-10 entity chain must not cause OOM / hang.

    The first line of defence is the ``is_ssml`` regex (``<speak``
    must be first). For DOCTYPE-prefixed payloads ``is_ssml`` returns
    False and the input is returned verbatim as a single plain-text
    segment — no XML parsing, no expansion.
    """

    @staticmethod
    def _build_billion_laughs(depth: int = 9, fanout: int = 10) -> str:
        decls = ['<!ENTITY lol "lol">']
        prev = "lol"
        for d in range(2, depth + 1):
            kids = "".join(f"&{prev};" for _ in range(fanout))
            name = f"lol{d}"
            decls.append(f'<!ENTITY {name} "{kids}">')
            prev = name
        return f"<!DOCTYPE lolz [{''.join(decls)}]><speak>&{prev};</speak>"

    def test_billion_laughs_bounded(self):
        payload = self._build_billion_laughs(depth=9, fanout=10)
        # Must not OOM or hang. Bounded time / memory.
        segments = SSMLParser.parse(payload)
        assert len(segments) >= 1
        # The whole payload may be returned as plain text (since the
        # is_ssml regex check rejects DOCTYPE-prefixed input). No
        # entity expansion occurred — so the output cannot exceed the
        # input length by more than a small constant.
        full_text = _all_text(segments)
        # Entity expansion would yield 10**9 = 1B chars. Pin upper bound
        # at 2x input length to confirm no expansion.
        assert len(full_text) <= len(payload) * 2

    def test_billion_laughs_speak_first_falls_back_safely(self):
        """If the DOCTYPE were inlined inside <speak>, ET would raise.

        We construct an even smaller variant and verify the parser
        either rejects via ``is_ssml`` or returns ParseError fallback.
        """
        # Internal entity ref without DOCTYPE — undefined entity.
        payload = '<speak><prosody rate="slow">&lol;&lol;&lol;</prosody></speak>'
        segments = SSMLParser.parse(payload)
        assert len(segments) >= 1
        full_text = _all_text(segments)
        # Should not have ballooned. Small bound regardless of fallback path.
        assert len(full_text) < 1000


# =====================================================================
# DTD — external SYSTEM declaration
# =====================================================================


class TestDtdInlineSafelyHandled:
    """``<!DOCTYPE speak SYSTEM "external.dtd">`` must not fetch the DTD."""

    def test_dtd_inline_safely_handled(self):
        payload = (
            '<!DOCTYPE speak SYSTEM "http://example.invalid/external.dtd">'
            "<speak>Hello</speak>"
        )
        # Must complete quickly (no network fetch).
        segments = SSMLParser.parse(payload)
        assert len(segments) >= 1
        # Text content "Hello" should be retrievable somehow — either
        # via the plain-text fallback (whole payload) or via successful
        # parsing of the inner <speak>. Both are acceptable.
        full_text = _all_text(segments)
        assert "Hello" in full_text or "speak" in full_text

    def test_dtd_external_with_xml_prolog(self):
        payload = (
            '<?xml version="1.0"?>'
            '<!DOCTYPE speak SYSTEM "http://example.invalid/external.dtd">'
            "<speak>Hello</speak>"
        )
        segments = SSMLParser.parse(payload)
        assert len(segments) >= 1


# =====================================================================
# Processing instruction
# =====================================================================


class TestXmlProcessingInstructionIgnored:
    """``<?xml-stylesheet ... ?>`` must not trigger any XSL fetching."""

    def test_xml_processing_instruction_ignored(self):
        payload = (
            '<?xml-stylesheet type="text/xsl" href="evil.xsl"?><speak>Hello</speak>'
        )
        # No fetch / no error / completes quickly.
        segments = SSMLParser.parse(payload)
        assert len(segments) >= 1
        full_text = _all_text(segments)
        # "Hello" should be present somewhere (either as parsed text or
        # as part of the plain-text fallback containing the full payload).
        assert "Hello" in full_text

    def test_xml_prolog_only(self):
        # Bare xml prolog before <speak>.
        payload = '<?xml version="1.0" encoding="UTF-8"?><speak>Hi</speak>'
        segments = SSMLParser.parse(payload)
        assert len(segments) >= 1


# =====================================================================
# Attribute with entity reference
# =====================================================================


class TestAttributeWithEntityReference:
    """Entity refs in attribute values: ``&amp;`` ok, ``&xxe;`` rejected."""

    def test_attribute_with_amp_entity_allowed(self):
        # Predefined entity &amp; is always valid in XML.
        payload = '<speak><break time="&amp;500ms"/></speak>'
        segments = SSMLParser.parse(payload)
        # Should not crash. The attribute value resolves to "&500ms",
        # which the break-time parser rejects as invalid (-> 0ms),
        # so the empty break is filtered out by merge.
        # We only assert that no panic / unbounded behaviour occurs.
        assert isinstance(segments, list)

    def test_attribute_with_xxe_entity_falls_back(self):
        payload = (
            '<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
            '<speak><break time="&xxe;"/></speak>'
        )
        segments = SSMLParser.parse(payload)
        assert len(segments) >= 1
        full_text = _all_text(segments)
        assert "root:" not in full_text

    def test_attribute_with_undeclared_entity_speak_first(self):
        """``<speak>`` first; undeclared entity in attr triggers ParseError."""
        payload = '<speak><break time="&xxe;"/></speak>'
        segments = SSMLParser.parse(payload)
        # Falls back to stripped plain text — must not crash.
        assert len(segments) >= 1
        full_text = _all_text(segments)
        assert "root:" not in full_text


# =====================================================================
# Oversized input
# =====================================================================


class TestOversizedInputRaises:
    """Oversized SSML must raise ValueError (mitigates DoS)."""

    def test_oversized_input_raises(self):
        # 100KB+1 of 'A' inside <speak> wrappers.
        ssml = "<speak>" + "A" * (_MAX_SSML_SIZE + 1) + "</speak>"
        with pytest.raises(ValueError, match="SSML input too large"):
            SSMLParser.parse(ssml)

    def test_oversized_billion_laughs_raises_or_falls_back(self):
        """A DOCTYPE-prefixed billion laughs ~ size cap behaviour.

        If the payload exceeds ``_MAX_SSML_SIZE`` AND the ``is_ssml``
        regex returns True (i.e. ``<speak>`` happens to be at the
        start), the size limit is enforced. If the regex returns False
        (DOCTYPE first), the input is returned as plain text — and the
        size check does not apply (existing
        ``test_plain_text_skips_size_check`` regression).

        Here we force the SSML branch by constructing a payload where
        ``<speak>`` is the first token but is followed by a huge body.
        """
        # is_ssml true, oversized -> ValueError
        big_body = "B" * (_MAX_SSML_SIZE + 100)
        ssml = f"<speak>{big_body}</speak>"
        with pytest.raises(ValueError, match="SSML input too large"):
            SSMLParser.parse(ssml)


# =====================================================================
# Cross-runtime drift sentinels
# =====================================================================


class TestCrossRuntimeDriftSentinels:
    """Cases shared with Rust / C# / Go test suites for drift detection.

    If any of these change, double-check that the analogous tests in
    other runtimes still pass and that the change is intentional.
    """

    def test_doctype_prefix_treated_as_plain_text(self):
        """DOCTYPE-prefixed payloads bypass XML parsing entirely.

        Pinned: ``is_ssml`` regex requires ``<speak`` to be the first
        non-whitespace token. The Rust / Go regexes are identical
        (``^\\s*<speak[\\s>]``), and C# uses the same pattern via
        ``GeneratedRegex``. This guarantees the four runtimes agree on
        the rejection criterion.
        """
        cases = [
            "<!DOCTYPE speak><speak>Hi</speak>",
            "<!DOCTYPE foo [<!ENTITY x 'y'>]><speak>Hi</speak>",
            "<?xml version='1.0'?><speak>Hi</speak>",
            "<?xml-stylesheet href='x.xsl'?><speak>Hi</speak>",
        ]
        for payload in cases:
            assert SSMLParser.is_ssml(payload) is False, (
                f"unexpected is_ssml=True for {payload!r}"
            )
            segments = SSMLParser.parse(payload)
            assert len(segments) == 1
            assert segments[0].text == payload

    def test_speak_first_undeclared_entity_consistent(self):
        """``<speak>&undefined;</speak>`` must yield a stripped fallback.

        Pinned: implementations vary in the *exact* text of the
        fallback (Python returns ``&xxe;``, Rust currently returns
        empty, Go returns ``&xxe;``, C# returns ``&xxe;`` — all are
        acceptable and not in the user-visible attack surface). All
        four MUST return at least one segment and MUST NOT crash.
        """
        payload = "<speak>&xxe;</speak>"
        segments = SSMLParser.parse(payload)
        assert isinstance(segments, list)
        assert len(segments) >= 1
        full_text = _all_text(segments)
        # No file / network content leaked.
        assert "root:" not in full_text
        assert "/bin/" not in full_text
