.PHONY: install run fmt test check

install:
	go mod download

run:
	go run .

fmt:
	gofmt -w .

test:
	go test ./...

check:
	go vet ./...
	go test -race ./...
