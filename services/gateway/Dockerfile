FROM golang:1.25.4-alpine AS build

WORKDIR /src

COPY libs/httpx/go.mod ./libs/httpx/go.mod
COPY services/gateway/go.mod services/gateway/go.sum ./services/gateway/

WORKDIR /src/services/gateway

RUN go mod download

WORKDIR /src

COPY libs/httpx ./libs/httpx
COPY services/gateway ./services/gateway

WORKDIR /src/services/gateway

RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/gateway .

FROM alpine:3.22

RUN apk add --no-cache ca-certificates && \
    addgroup -S -g 10001 gateway && \
    adduser -S -D -H -u 10001 -G gateway gateway

COPY --from=build --chown=gateway:gateway /out/gateway /usr/local/bin/gateway

USER gateway:gateway

EXPOSE 8080

ENTRYPOINT ["/usr/local/bin/gateway"]
