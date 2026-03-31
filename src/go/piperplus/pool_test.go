package piperplus

import (
	"context"
	"sync"
	"sync/atomic"
	"testing"
)

func TestNewVoicePool(t *testing.T) {
	pool := NewVoicePool("/tmp/model.onnx", 4)

	if pool.modelPath != "/tmp/model.onnx" {
		t.Errorf("modelPath = %q, want %q", pool.modelPath, "/tmp/model.onnx")
	}
	if cap(pool.sem) != 4 {
		t.Errorf("sem capacity = %d, want 4", cap(pool.sem))
	}
	if cap(pool.voices) != 4 {
		t.Errorf("voices capacity = %d, want 4", cap(pool.voices))
	}
	if pool.closed {
		t.Error("closed = true, want false")
	}
}

func TestNewVoicePool_MinConcurrency(t *testing.T) {
	pool := NewVoicePool("/tmp/model.onnx", 0)

	if cap(pool.sem) != 1 {
		t.Errorf("sem capacity = %d, want 1 (clamped from 0)", cap(pool.sem))
	}
}

func TestVoicePool_Close(t *testing.T) {
	pool := NewVoicePool("/tmp/model.onnx", 2)

	t.Run("FirstClose", func(t *testing.T) {
		if err := pool.Close(); err != nil {
			t.Errorf("Close() = %v, want nil", err)
		}
		if !pool.closed {
			t.Error("closed = false after Close()")
		}
	})

	t.Run("IdempotentClose", func(t *testing.T) {
		if err := pool.Close(); err != nil {
			t.Errorf("second Close() = %v, want nil", err)
		}
	})

	t.Run("SynthesizeAfterClose", func(t *testing.T) {
		_, err := pool.Synthesize(context.Background(), "hello")
		if err != ErrPoolClosed {
			t.Errorf("Synthesize after Close: err = %v, want ErrPoolClosed", err)
		}
	})

	t.Run("SynthesizeFromIDsAfterClose", func(t *testing.T) {
		req := &SynthesisRequest{PhonemeIDs: []int64{1, 2, 3}}
		_, err := pool.SynthesizeFromIDs(context.Background(), req)
		if err != ErrPoolClosed {
			t.Errorf("SynthesizeFromIDs after Close: err = %v, want ErrPoolClosed", err)
		}
	})
}

func TestVoicePool_ConcurrencyLimit(t *testing.T) {
	const concurrency = 3
	pool := NewVoicePool("/tmp/model.onnx", concurrency)
	defer pool.Close()

	var active atomic.Int32
	var maxActive atomic.Int32
	var wg sync.WaitGroup

	// Fill up all semaphore slots manually to verify the limit.
	for i := 0; i < concurrency; i++ {
		pool.sem <- struct{}{}
	}

	// Launch goroutines that try to acquire the semaphore.
	const workers = 6
	ready := make(chan struct{})

	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-ready
			pool.sem <- struct{}{} // acquire
			cur := active.Add(1)
			for {
				old := maxActive.Load()
				if cur <= old || maxActive.CompareAndSwap(old, cur) {
					break
				}
			}
			active.Add(-1)
			<-pool.sem // release
		}()
	}

	// Release all slots and let workers compete.
	for i := 0; i < concurrency; i++ {
		<-pool.sem
	}
	close(ready)
	wg.Wait()

	if got := maxActive.Load(); got > int32(concurrency) {
		t.Errorf("max concurrent = %d, want <= %d", got, concurrency)
	}
}

func TestVoicePool_AcquireRespectsContext(t *testing.T) {
	pool := NewVoicePool("/tmp/model.onnx", 1)
	defer pool.Close()

	// Fill the semaphore so the next acquire must block.
	pool.sem <- struct{}{}

	ctx, cancel := context.WithCancel(context.Background())
	cancel() // cancel immediately

	_, err := pool.acquire(ctx)
	if err != context.Canceled {
		t.Errorf("acquire with canceled ctx: err = %v, want context.Canceled", err)
	}

	// Drain the semaphore for clean teardown.
	<-pool.sem
}
