package main

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/spf13/cobra"

	"github.com/ayutaz/piper-plus/src/go/piperplus"
)

var serveAddr string

var serveCmd = &cobra.Command{
	Use:   "serve",
	Short: "Start HTTP TTS server",
	Long: `Start an HTTP server that exposes TTS synthesis via REST API.

Endpoints:
  GET/POST /synthesize  Synthesize text to WAV audio
  GET      /health      Health check
  GET      /info        Model information`,
	RunE: runServe,
}

func init() {
	serveCmd.Flags().StringVar(&serveAddr, "addr", ":8080", "listen address (host:port)")
}

func runServe(cmd *cobra.Command, args []string) error {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	// Configure logging.
	level := slog.LevelInfo
	if debug {
		level = slog.LevelDebug
	}
	if quiet {
		level = slog.LevelError + 1
	}
	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: level}))

	// Resolve model path: flag > env.
	resolvedModel := modelPath
	if resolvedModel == "" {
		resolvedModel = os.Getenv("PIPER_DEFAULT_MODEL")
	}
	if resolvedModel == "" {
		return fmt.Errorf("model path required: specify --model or set $PIPER_DEFAULT_MODEL")
	}

	// Try resolving model name/alias if file doesn't exist.
	if _, err := os.Stat(resolvedModel); os.IsNotExist(err) {
		mgr := piperplus.NewModelManager(modelDir, logger)
		resolved, resolveErr := mgr.FindModel(resolvedModel)
		if resolveErr != nil {
			return fmt.Errorf("model not found: %s (try --list-models or --download-model)", resolvedModel)
		}
		resolvedModel = resolved
	}

	// Initialize ONNX Runtime.
	if err := piperplus.Init(""); err != nil {
		return fmt.Errorf("failed to initialize ONNX Runtime: %w", err)
	}
	defer piperplus.Shutdown() //nolint:errcheck

	// Load voice.
	var loadOpts []piperplus.LoadOption
	if configPath != "" {
		loadOpts = append(loadOpts, piperplus.WithConfig(configPath))
	}
	loadOpts = append(loadOpts, piperplus.WithDevice(device))
	loadOpts = append(loadOpts, piperplus.WithLogger(logger))
	if len(customDictPaths) > 0 {
		loadOpts = append(loadOpts, piperplus.WithCustomDict(customDictPaths...))
	}

	voice, err := piperplus.LoadVoice(ctx, resolvedModel, loadOpts...)
	if err != nil {
		return fmt.Errorf("failed to load voice: %w", err)
	}
	defer voice.Close() //nolint:errcheck

	// Start server.
	ttsServer := piperplus.NewServer(voice, logger)
	fmt.Fprintf(os.Stderr, "Starting TTS server on %s\n", serveAddr)
	fmt.Fprintln(os.Stderr, "Endpoints:")
	fmt.Fprintln(os.Stderr, "  GET/POST /synthesize?text=...&lang=...")
	fmt.Fprintln(os.Stderr, "  GET      /health")
	fmt.Fprintln(os.Stderr, "  GET      /info")

	httpServer := &http.Server{
		Addr:    serveAddr,
		Handler: ttsServer.Handler(),
	}

	errCh := make(chan error, 1)
	go func() {
		if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			errCh <- err
		}
		close(errCh)
	}()

	select {
	case err := <-errCh:
		return err
	case <-ctx.Done():
		logger.Info("shutting down server")
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		return httpServer.Shutdown(shutdownCtx)
	}
}
