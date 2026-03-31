package piperplus

import (
	"context"
	"fmt"
	"sync"
)

// ErrPoolClosed is returned when Synthesize is called on a closed VoicePool.
var ErrPoolClosed = fmt.Errorf("piperplus: voice pool is closed")

// VoicePool manages a pool of Voice instances for concurrent synthesis,
// modeled after database/sql.DB. Voices are created lazily and recycled.
type VoicePool struct {
	modelPath string
	loadOpts  []LoadOption
	sem       chan struct{} // semaphore limiting concurrency
	voices    chan *Voice   // recycled voices
	mu        sync.Mutex
	closed    bool
	inflight  sync.WaitGroup // tracks in-flight acquire/release operations
}

// NewVoicePool creates a pool with the specified concurrency limit.
func NewVoicePool(modelPath string, concurrency int, opts ...LoadOption) *VoicePool {
	if concurrency < 1 {
		concurrency = 1
	}
	return &VoicePool{
		modelPath: modelPath,
		loadOpts:  opts,
		sem:       make(chan struct{}, concurrency),
		voices:    make(chan *Voice, concurrency),
	}
}

// Synthesize acquires a voice, synthesizes text, and returns the voice.
func (p *VoicePool) Synthesize(ctx context.Context, text string, opts ...SynthesisOption) (*SynthesisResult, error) {
	v, err := p.acquire(ctx)
	if err != nil {
		return nil, err
	}
	defer p.release(v)
	return v.Synthesize(ctx, text, opts...)
}

// SynthesizeFromIDs acquires a voice and synthesizes from phoneme IDs.
func (p *VoicePool) SynthesizeFromIDs(ctx context.Context, req *SynthesisRequest) (*SynthesisResult, error) {
	v, err := p.acquire(ctx)
	if err != nil {
		return nil, err
	}
	defer p.release(v)
	return v.SynthesizeFromIDs(ctx, req)
}

// Close closes all pooled voices and prevents new acquisitions.
// It waits for all in-flight operations to finish before draining the pool.
// Idempotent.
func (p *VoicePool) Close() error {
	p.mu.Lock()
	if p.closed {
		p.mu.Unlock()
		return nil
	}
	p.closed = true
	p.mu.Unlock()

	// Wait for all in-flight acquire/release operations to complete
	// before draining the channel. This ensures no goroutine will
	// attempt to send on p.voices after we close it.
	p.inflight.Wait()

	close(p.voices)
	var firstErr error
	for v := range p.voices {
		if err := v.Close(); err != nil && firstErr == nil {
			firstErr = err
		}
	}
	return firstErr
}

// acquire gets a voice from the pool or creates a new one.
func (p *VoicePool) acquire(ctx context.Context) (*Voice, error) {
	p.mu.Lock()
	if p.closed {
		p.mu.Unlock()
		return nil, ErrPoolClosed
	}
	// Register in-flight operation while still holding the lock,
	// so Close() cannot proceed past inflight.Wait() until we are done.
	p.inflight.Add(1)
	p.mu.Unlock()

	// On any error path below, we must call inflight.Done().
	ok := false
	defer func() {
		if !ok {
			p.inflight.Done()
		}
	}()

	// Acquire a semaphore slot (bounded concurrency).
	select {
	case p.sem <- struct{}{}:
	case <-ctx.Done():
		return nil, ctx.Err()
	}

	// Double-check: pool may have been closed between the first check
	// and semaphore acquisition (TOCTOU fix).
	p.mu.Lock()
	if p.closed {
		p.mu.Unlock()
		<-p.sem
		return nil, ErrPoolClosed
	}
	p.mu.Unlock()

	// Try to reuse a recycled voice.
	select {
	case v := <-p.voices:
		ok = true
		return v, nil
	default: // no recycled voice available
	}

	// Create a new voice. If LoadVoice fails, return the semaphore slot.
	v, err := LoadVoice(ctx, p.modelPath, p.loadOpts...)
	if err != nil {
		<-p.sem
		return nil, err
	}
	ok = true
	return v, nil
}

// release returns a voice to the pool or closes it if the pool is full.
func (p *VoicePool) release(v *Voice) {
	// Always return the semaphore slot and mark inflight done, even on panic.
	defer func() {
		<-p.sem
		p.inflight.Done()
	}()

	// Check closed under lock. If closed, close the voice directly
	// instead of sending to the (potentially closed) channel.
	p.mu.Lock()
	if p.closed {
		p.mu.Unlock()
		_ = v.Close()
		return
	}
	p.mu.Unlock()

	select {
	case p.voices <- v:
	default:
		_ = v.Close()
	}
}
