.PHONY: build test test-race test-integration lint vet fmt clean install docker

# Variables
BINARY := piper-plus
BUILD_DIR := build
GO := go
GOFLAGS := -race
VERSION := $(shell git describe --tags --always --dirty 2>/dev/null || echo "dev")
LDFLAGS := -ldflags "-X main.version=$(VERSION)"

## Build targets

build: ## Build CLI binary
	$(GO) build $(LDFLAGS) -o $(BUILD_DIR)/$(BINARY) ./cmd/piper-plus

install: ## Install CLI to GOPATH/bin
	$(GO) install $(LDFLAGS) ./cmd/piper-plus

## Test targets

test: ## Run unit tests
	$(GO) test -v -count=1 ./...

test-race: ## Run unit tests with race detector
	$(GO) test -v -race -count=1 ./...

test-integration: ## Run integration tests (requires ONNX Runtime + model)
	$(GO) test -v -race -count=1 -tags integration ./...

test-all: test-integration ## Run all tests

## Code quality

vet: ## Run go vet
	$(GO) vet ./...

fmt: ## Format code
	gofmt -w .

lint: ## Run golangci-lint
	golangci-lint run ./...

## Docker

docker: ## Build Docker image
	docker build -t piper-plus-go -f docker/Dockerfile ../..

docker-run: ## Run Docker container (example)
	docker run --rm -v $(PWD)/models:/models piper-plus-go -m /models/model.onnx -t "Hello"

## Clean

clean: ## Remove build artifacts
	rm -rf $(BUILD_DIR)
	$(GO) clean -cache -testcache

## Coverage

coverage: ## Generate test coverage report
	$(GO) test -coverprofile=coverage.out ./...
	$(GO) tool cover -html=coverage.out -o coverage.html
	@echo "Coverage report: coverage.html"

## Help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
