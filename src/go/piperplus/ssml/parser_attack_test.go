// Adversarial tests for the ssml package — XXE / billion-laughs / DTD / PI.
//
// These tests pin the *current* defensive behaviour of Parse against
// well-known XML attack vectors. The cases mirror analogous fixtures in
// the Python / Rust / C# runtimes so cross-runtime drift can be detected.
//
// Contract for each case:
//  1. The parser MUST NOT crash, panic, segfault, OOM, or hang.
//  2. The parser MUST NOT expand external entities (file://, http://, ...).
//  3. Either the input is rejected by IsSSML() (DOCTYPE / xml prolog
//     precedes <speak>) and returned as a single plain-text segment,
//     OR encoding/xml returns an error and Parse falls back to stripped
//     plain text. In both branches no entity reference value leaks.
//
// encoding/xml behaviour pinned here:
//   - Undeclared entity references -> "invalid character entity" error
//     -> Parse fallback -> stripped plain text segment.
//   - DOCTYPE Directive -> emitted as xml.Directive, ignored by walk().
//   - Stylesheet PI -> emitted as xml.ProcInst, ignored by walk().
//   - SYSTEM external IDs -> never auto-fetched.

package ssml

import (
	"strings"
	"testing"
	"time"
)

// allText concatenates segment text for substring search.
func allText(segments []Segment) string {
	parts := make([]string, len(segments))
	for i, s := range segments {
		parts[i] = s.Text
	}
	return strings.Join(parts, " ")
}

// =====================================================================
// XXE — external entity attack
// =====================================================================

func TestAttack_XxeExternalEntityBlocked(t *testing.T) {
	// Standard XXE payload (DOCTYPE + xml prolog).
	payload := `<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><speak>&xxe;</speak>`

	segments := Parse(payload)
	if len(segments) == 0 {
		t.Fatal("must produce at least one segment")
	}

	// No /etc/passwd content should leak.
	full := allText(segments)
	for _, marker := range []string{"root:", "/bin/bash", "/bin/sh"} {
		if strings.Contains(full, marker) {
			t.Errorf("file content marker %q leaked into output: %q", marker, full)
		}
	}
}

func TestAttack_XxeDoctypeOnlyNoXmlProlog(t *testing.T) {
	// DOCTYPE without xml prolog: same protection.
	payload := `<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><speak>&xxe;</speak>`

	segments := Parse(payload)
	if len(segments) == 0 {
		t.Fatal("must produce at least one segment")
	}

	full := allText(segments)
	if strings.Contains(full, "root:") {
		t.Errorf("/etc/passwd content leaked: %q", full)
	}
}

func TestAttack_XxeSpeakFirstUndeclaredEntity(t *testing.T) {
	// <speak> first with undeclared entity: encoding/xml returns
	// "invalid character entity" -> Parse fallback -> stripped text.
	payload := `<speak>&xxe;</speak>`

	segments := Parse(payload)
	if len(segments) == 0 {
		t.Fatal("must produce at least one segment")
	}

	full := allText(segments)
	for _, marker := range []string{"root:", "/etc/passwd", "/bin/"} {
		if strings.Contains(full, marker) {
			t.Errorf("file content marker %q leaked: %q", marker, full)
		}
	}
}

// =====================================================================
// Billion laughs — exponential entity expansion DoS
// =====================================================================

func buildBillionLaughs(depth, fanout int) string {
	var decls strings.Builder
	decls.WriteString(`<!ENTITY lol "lol">`)
	prev := "lol"
	for d := 2; d <= depth; d++ {
		var kids strings.Builder
		for i := 0; i < fanout; i++ {
			kids.WriteByte('&')
			kids.WriteString(prev)
			kids.WriteByte(';')
		}
		name := "lol" + itoa(d)
		decls.WriteString(`<!ENTITY `)
		decls.WriteString(name)
		decls.WriteString(` "`)
		decls.WriteString(kids.String())
		decls.WriteString(`">`)
		prev = name
	}
	return `<!DOCTYPE lolz [` + decls.String() + `]><speak>&` + prev + `;</speak>`
}

// itoa avoids importing strconv just for one cast.
func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	digits := []byte{}
	for n > 0 {
		digits = append([]byte{byte('0' + n%10)}, digits...)
		n /= 10
	}
	return string(digits)
}

func TestAttack_BillionLaughsBounded(t *testing.T) {
	// 9-deep, fan-out 10. Naive expansion = 10^9 = 1B chars. The IsSSML
	// regex (^\s*<speak[\s>]) rejects DOCTYPE-prefixed input, so the
	// payload is returned verbatim as plain text — no expansion.
	payload := buildBillionLaughs(9, 10)

	start := time.Now()
	segments := Parse(payload)
	elapsed := time.Since(start)

	if elapsed > 5*time.Second {
		t.Fatalf("billion laughs took too long: %v", elapsed)
	}
	if len(segments) == 0 {
		t.Fatal("must produce at least one segment")
	}

	full := allText(segments)
	// No expansion can have occurred — output bounded relative to input.
	if len(full) > len(payload)*2 {
		t.Errorf("output ballooned: input=%d, output=%d",
			len(payload), len(full))
	}
}

func TestAttack_BillionLaughsSpeakFirstFallsBackSafely(t *testing.T) {
	// <speak>-first variant: undefined entity refs reach encoding/xml,
	// which raises "invalid character entity" and Parse falls back to
	// stripped plain text — no expansion possible. Mirrors the Python
	// test_billion_laughs_speak_first_falls_back_safely parity case so
	// that all 4 runtimes lock in the no-expansion guarantee even when
	// the DOCTYPE shield does not fire.
	payload := `<speak><prosody rate="slow">&lol;&lol;&lol;</prosody></speak>`

	segments := Parse(payload)
	if len(segments) == 0 {
		t.Fatal("must produce at least one segment")
	}
	full := allText(segments)
	if len(full) >= 1000 {
		t.Errorf("speak-first billion-laughs ballooned: %d", len(full))
	}
}

// =====================================================================
// DTD — external SYSTEM declaration
// =====================================================================

func TestAttack_ExternalDtdNotFetched(t *testing.T) {
	// encoding/xml emits a Directive token for DOCTYPE, never fetches
	// external SYSTEM IDs. IsSSML regex rejects DOCTYPE-prefixed input
	// as a first defence.
	payload := `<!DOCTYPE speak SYSTEM "http://example.invalid/external.dtd"><speak>Hello</speak>`

	start := time.Now()
	segments := Parse(payload)
	elapsed := time.Since(start)

	// No network fetch — must complete fast.
	if elapsed > time.Second {
		t.Fatalf("DTD parse took too long (network fetch?): %v", elapsed)
	}
	if len(segments) == 0 {
		t.Fatal("must produce at least one segment")
	}

	full := allText(segments)
	if !strings.Contains(full, "Hello") && !strings.Contains(full, "speak") {
		t.Errorf("expected text recoverable, got: %q", full)
	}
}

func TestAttack_ExternalDtdWithXmlPrologNotFetched(t *testing.T) {
	// External SYSTEM DTD preceded by an XML prolog. Mirrors the Python
	// test_dtd_external_with_xml_prolog and C# ExternalDtdWithXmlProlog_NotFetched
	// parity cases so all 4 runtimes share both DTD shapes (with and
	// without prolog).
	payload := `<?xml version="1.0"?><!DOCTYPE speak SYSTEM "http://example.invalid/external.dtd"><speak>Hello</speak>`

	start := time.Now()
	segments := Parse(payload)
	elapsed := time.Since(start)

	if elapsed > time.Second {
		t.Fatalf("DTD-with-prolog parse took too long: %v", elapsed)
	}
	if len(segments) == 0 {
		t.Fatal("must produce at least one segment")
	}
}

// =====================================================================
// Processing instruction
// =====================================================================

func TestAttack_XmlStylesheetPiIgnored(t *testing.T) {
	// <?xml-stylesheet?> must not trigger any XSL fetching. IsSSML regex
	// rejects input that starts with `<?` (not <speak).
	payload := `<?xml-stylesheet type="text/xsl" href="evil.xsl"?><speak>Hello</speak>`

	start := time.Now()
	segments := Parse(payload)
	elapsed := time.Since(start)

	if elapsed > time.Second {
		t.Fatalf("PI parse took too long: %v", elapsed)
	}
	if len(segments) == 0 {
		t.Fatal("must produce at least one segment")
	}

	full := allText(segments)
	if !strings.Contains(full, "Hello") {
		t.Errorf("expected 'Hello' in output, got: %q", full)
	}
}

func TestAttack_XmlPrologOnly(t *testing.T) {
	// Bare XML prolog with no DOCTYPE. The IsSSML regex still rejects
	// input prefixed by `<?` (not <speak), so the payload is returned
	// verbatim as plain text. Mirrors the Python test_xml_prolog_only
	// parity case.
	payload := `<?xml version="1.0" encoding="UTF-8"?><speak>Hi</speak>`

	segments := Parse(payload)
	if len(segments) == 0 {
		t.Fatal("must produce at least one segment")
	}
}

// =====================================================================
// Attribute with entity reference
// =====================================================================

func TestAttack_AttributeWithEntityReference(t *testing.T) {
	// Predefined entity &amp; in attribute value — must not crash.
	payloadAmp := `<speak><break time="&amp;500ms"/></speak>`
	segments := Parse(payloadAmp)
	if segments == nil {
		t.Fatal("Parse returned nil for &amp; attr")
	}

	// Undefined entity in attribute — encoding/xml errors, fallback
	// stripped text. Must not crash, must not leak.
	payloadXxe := `<speak><break time="&xxe;"/></speak>`
	segments = Parse(payloadXxe)
	full := allText(segments)
	for _, marker := range []string{"root:", "/etc/passwd"} {
		if strings.Contains(full, marker) {
			t.Errorf("entity expansion leaked %q: %q", marker, full)
		}
	}
}

func TestAttack_AttributeWithXxeEntityDoctypePrefix(t *testing.T) {
	// DOCTYPE-prefixed XXE inside a <break> attribute. IsSSML rejects
	// the DOCTYPE prefix → plain text. The &xxe; token must NEVER
	// resolve to file content. Mirrors Python
	// test_attribute_with_xxe_entity_falls_back and C#
	// AttributeWithXxeEntity_DoctypePrefix_FallsBackSafely so all 4
	// runtimes pin the same observable behaviour.
	payload := `<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><speak><break time="&xxe;"/></speak>`

	segments := Parse(payload)
	if len(segments) == 0 {
		t.Fatal("must produce at least one segment")
	}
	full := allText(segments)
	for _, marker := range []string{"root:", "/bin/"} {
		if strings.Contains(full, marker) {
			t.Errorf("DOCTYPE-prefixed XXE attr leaked %q: %q", marker, full)
		}
	}
}

// =====================================================================
// Cross-runtime drift sentinel
// =====================================================================

func TestAttack_DoctypePrefixTreatedAsPlainText(t *testing.T) {
	// IsSSML regex (^\s*<speak[\s>]) is identical across all four
	// runtimes. If this test changes, double-check Python / Rust / C#
	// analogues for drift.
	cases := []string{
		`<!DOCTYPE speak><speak>Hi</speak>`,
		`<!DOCTYPE foo [<!ENTITY x 'y'>]><speak>Hi</speak>`,
		`<?xml version='1.0'?><speak>Hi</speak>`,
		`<?xml-stylesheet href='x.xsl'?><speak>Hi</speak>`,
	}
	for _, payload := range cases {
		if IsSSML(payload) {
			t.Errorf("unexpected IsSSML=true for %q", payload)
		}
		segments := Parse(payload)
		if len(segments) != 1 {
			t.Errorf("expected 1 segment for %q, got %d", payload, len(segments))
			continue
		}
		if segments[0].Text != payload {
			t.Errorf("expected text=payload for %q, got %q",
				payload, segments[0].Text)
		}
	}
}
