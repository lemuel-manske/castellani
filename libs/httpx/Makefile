.PHONY: install fmt test check

install:
	go mod download

fmt:
	go fmt ./...

test:
	go test ./...

check:
	go vet ./...
	go test -race ./...
