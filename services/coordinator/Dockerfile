FROM golang:1.25.4-alpine AS build

WORKDIR /src

COPY libs/httpx/go.mod ./libs/httpx/go.mod
COPY services/coordinator/go.mod services/coordinator/go.sum ./services/coordinator/

WORKDIR /src/services/coordinator

RUN go mod download

WORKDIR /src

COPY libs/httpx ./libs/httpx
COPY services/coordinator ./services/coordinator

WORKDIR /src/services/coordinator

RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/coordinator .

FROM alpine:3.22

RUN apk add --no-cache ca-certificates \
    && addgroup -S -g 10001 coordinator \
    && adduser -S -D -H -u 10001 -G coordinator coordinator

COPY --from=build --chown=coordinator:coordinator /out/coordinator /usr/local/bin/coordinator

USER coordinator:coordinator

EXPOSE 8081

ENTRYPOINT ["/usr/local/bin/coordinator"]
