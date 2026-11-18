.PHONY: install run fmt test check

install:
	go mod download

run:
	go run .

fmt:
	go fmt ./...

test:
	go test ./...

check:
	go vet ./...
	go test -race ./...
