package phonemize

// NewOpenJTalkEngine creates a JapaneseG2PEngine backed by OpenJTalk via CGO.
// It is nil when the binary is built without the "openjtalk" build tag.
// When non-nil, it accepts a dictionary directory path and returns an engine.
var NewOpenJTalkEngine func(dictPath string) (JapaneseG2PEngine, error)
