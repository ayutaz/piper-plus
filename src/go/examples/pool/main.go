// Example: Concurrent synthesis using VoicePool.
//
// Usage:
//
//	export ONNX_RUNTIME_SHARED_LIBRARY_PATH=/path/to/libonnxruntime.so
//	go run . -model model.onnx -concurrency 4
package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"sync"
	"time"

	"github.com/ayutaz/piper-plus/src/go/piperplus"
)

func main() {
	modelPath := flag.String("model", "", "Path to ONNX model")
	concurrency := flag.Int("concurrency", 4, "Number of concurrent voices")
	outDir := flag.String("outdir", "output", "Output directory")
	language := flag.String("lang", "en", "Language")
	flag.Parse()

	if *modelPath == "" {
		log.Fatal("--model required")
	}

	if err := piperplus.Init(""); err != nil {
		log.Fatal(err)
	}
	defer piperplus.Shutdown()

	// Sample texts for concurrent synthesis
	texts := []string{
		"Hello, how are you today?",
		"The weather is beautiful.",
		"I love programming in Go.",
		"Piper Plus supports six languages.",
		"This is a concurrent synthesis example.",
		"Neural text-to-speech is amazing.",
		"Each sentence runs in parallel.",
		"Voice pooling improves throughput.",
	}

	// Create voice pool
	pool := piperplus.NewVoicePool(*modelPath, *concurrency)
	defer pool.Close()

	os.MkdirAll(*outDir, 0755)
	ctx := context.Background()
	start := time.Now()

	var wg sync.WaitGroup
	for i, text := range texts {
		wg.Add(1)
		go func(idx int, txt string) {
			defer wg.Done()

			result, err := pool.Synthesize(ctx, txt,
				piperplus.WithLanguage(*language))
			if err != nil {
				log.Printf("[%d] Error: %v", idx, err)
				return
			}

			outPath := filepath.Join(*outDir, fmt.Sprintf("pool_%03d.wav", idx+1))
			f, _ := os.Create(outPath)
			result.WriteTo(f)
			f.Close()

			fmt.Printf("[%d] %s (%.2fs, RTF=%.3f) %q\n",
				idx+1, outPath, result.Duration.Seconds(), result.RTF(), txt)
		}(i, text)
	}
	wg.Wait()

	fmt.Printf("\nAll %d utterances in %v (concurrency=%d)\n",
		len(texts), time.Since(start), *concurrency)
}
