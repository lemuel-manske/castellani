.PHONY: fmt test check style-check style-fix

fmt:
	go fmt ./...

test:
	go test ./...

check:
	go vet ./...
	go test -race ./...

style-check:
	go run ./cmd/gofmtx ../../libs/httpx ../../services/gateway

style-fix:
	go run ./cmd/gofmtx -w ../../libs/httpx ../../services/gateway
