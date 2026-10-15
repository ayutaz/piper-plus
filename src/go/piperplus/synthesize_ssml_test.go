package piperplus

import (
	"context"
	"reflect"
	"testing"
)

func TestSSMLSynthesisAppliesRateAndBreak(t *testing.T) {
	var texts []string
	var rates []float32
	result, err := synthesizeSSML(context.Background(), `<speak>A<break time="500ms"/><prosody rate="slow">B</prosody></speak>`, 1000, func(text string, rate float32) (*SynthesisResult, error) {
		texts = append(texts, text)
		rates = append(rates, rate)
		return &SynthesisResult{Audio: []int16{7, 8}, SampleRate: 1000}, nil
	})
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(texts, []string{"A", "B"}) || !reflect.DeepEqual(rates, []float32{1, 1.25}) {
		t.Fatalf("calls: %v %v", texts, rates)
	}
	if len(result.Audio) != 504 || result.Audio[1] != 8 || result.Audio[502] != 7 {
		t.Fatalf("break was not inserted: %v samples", len(result.Audio))
	}
	for _, sample := range result.Audio[2:502] {
		if sample != 0 {
			t.Fatal("break contains speech")
		}
	}
}

func TestSSMLSynthesisHonorsCancellation(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	_, err := synthesizeSSML(ctx, `<speak>A</speak>`, 1000, func(string, float32) (*SynthesisResult, error) { t.Fatal("called after cancellation"); return nil, nil })
	if err == nil {
		t.Fatal("expected cancellation")
	}
}
