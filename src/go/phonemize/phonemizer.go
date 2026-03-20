package phonemize

import "log/slog"

// ProsodyInfo holds A1/A2/A3 prosody values per phoneme.
type ProsodyInfo struct {
	A1 int // JA: accent relative pos; ZH: tone; EN/ES/FR/PT: 0
	A2 int // JA: mora pos in phrase; EN: stress (0/1/2); ES/FR/PT: stress (0/2); ZH: syllable pos
	A3 int // JA: phrase mora count; EN/ZH: word length; ES/FR/PT: word phoneme count
}

// PhonemizeResult holds phonemization output.
type PhonemizeResult struct {
	Tokens   []string       // phoneme tokens (may include PUA chars)
	Prosody  []*ProsodyInfo // parallel to Tokens; nil for non-linguistic tokens
	EOSToken string         // last EOS encountered ("$", "?", "?!", etc.)
}

// Phonemizer converts text to phoneme tokens with prosody.
type Phonemizer interface {
	PhonemizeWithProsody(text string) (*PhonemizeResult, error)
	LanguageCode() string
}

// TokensToIDs converts phoneme tokens to IDs using the phoneme_id_map.
// Tokens are first mapped through PUA (RegisterToken).
// Unknown tokens are skipped with a warning log.
func TokensToIDs(tokens []string, phonemeIDMap map[string][]int64) []int64 {
	var ids []int64
	for _, tok := range tokens {
		mapped := RegisterToken(tok)
		if idList, ok := phonemeIDMap[mapped]; ok {
			ids = append(ids, idList...)
		} else {
			slog.Warn("unknown phoneme token, skipping",
				"token", tok,
				"mapped", mapped,
			)
		}
	}
	return ids
}

// PostProcessIDs adds BOS/EOS markers and inter-phoneme padding.
// This is the default implementation used by EN, ZH, ES, FR, PT.
// Japanese handles BOS/EOS inline (no-op).
//
// Algorithm:
//  1. Intersperse padding: after each phoneme ID, insert pad token (ID 0 by default).
//     EXCEPT if the current ID is already a pad token (skip to avoid double-pad).
//     This produces the pattern: [ph1, pad, ph2, pad, ...] which VITS expects
//     for monotonic alignment search (MAS) to work correctly.
//  2. Prepend BOS + pad
//  3. Append EOS
func PostProcessIDs(
	phonemeIDs []int64,
	prosody []*ProsodyInfo,
	phonemeIDMap map[string][]int64,
	eosToken string,
) ([]int64, []*ProsodyInfo) {
	// Resolve special token IDs.
	padIDs := phonemeIDMap["_"]
	if len(padIDs) == 0 {
		padIDs = []int64{0}
	}
	padID := padIDs[0]

	bosIDs := phonemeIDMap["^"]

	eosIDs := phonemeIDMap[eosToken]
	if len(eosIDs) == 0 {
		eosIDs = phonemeIDMap["$"]
	}

	// Build a set of pad IDs for quick lookup.
	padSet := make(map[int64]bool, len(padIDs))
	for _, id := range padIDs {
		padSet[id] = true
	}

	// Step 1: Intersperse padding.
	var interspersedIDs []int64
	var interspersedProsody []*ProsodyInfo
	for i, id := range phonemeIDs {
		interspersedIDs = append(interspersedIDs, id)
		var p *ProsodyInfo
		if i < len(prosody) {
			p = prosody[i]
		}
		interspersedProsody = append(interspersedProsody, p)

		// Insert pad after this ID, unless it is itself a pad.
		if !padSet[id] {
			interspersedIDs = append(interspersedIDs, padID)
			interspersedProsody = append(interspersedProsody, nil)
		}
	}

	// Step 2: Prepend BOS + pad.
	prefixIDs := make([]int64, 0, len(bosIDs)+1)
	prefixProsody := make([]*ProsodyInfo, 0, len(bosIDs)+1)
	prefixIDs = append(prefixIDs, bosIDs...)
	for range bosIDs {
		prefixProsody = append(prefixProsody, nil)
	}
	prefixIDs = append(prefixIDs, padID)
	prefixProsody = append(prefixProsody, nil)

	// Step 3: Append EOS.
	resultIDs := make([]int64, 0, len(prefixIDs)+len(interspersedIDs)+len(eosIDs))
	resultProsody := make([]*ProsodyInfo, 0, len(prefixProsody)+len(interspersedProsody)+len(eosIDs))

	resultIDs = append(resultIDs, prefixIDs...)
	resultProsody = append(resultProsody, prefixProsody...)

	resultIDs = append(resultIDs, interspersedIDs...)
	resultProsody = append(resultProsody, interspersedProsody...)

	resultIDs = append(resultIDs, eosIDs...)
	for range eosIDs {
		resultProsody = append(resultProsody, nil)
	}

	return resultIDs, resultProsody
}
