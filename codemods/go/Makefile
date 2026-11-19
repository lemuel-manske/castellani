.PHONY: fmt test check apply

fmt:
	go fmt ./...

test:
	go test ./...

check:
	go vet ./...
	go test -race ./...

apply:
	go run ./cmd/gofmtx -w $(TARGET)
