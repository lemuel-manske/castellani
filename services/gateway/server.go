package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"sync/atomic"
	"time"

	"github.com/lemuel-manske/unnamed/services/gateway/api"
	"github.com/lemuel-manske/unnamed/services/gateway/application"
	"github.com/lemuel-manske/unnamed/services/gateway/internal/coordinator"
	"github.com/lemuel-manske/unnamed/services/gateway/internal/upstream"
)

const (
	serverReadHeaderTimeout = 5 * time.Second
	serverReadTimeout       = 15 * time.Second
	serverIdleTimeout       = 60 * time.Second
	serverMaxHeaderBytes    = 32 << 10
)

type gatewayServer struct {
	http            *http.Server
	ready           atomic.Bool
	shutdownTimeout time.Duration
}

func newGatewayServer(cfg config, logger *slog.Logger) *gatewayServer {
	gateway := &gatewayServer{shutdownTimeout: cfg.shutdownTimeout}
	coordinatorClient := coordinator.NewHTTPClient(*cfg.coordinatorURL, cfg.upstreamTimeout)
	app := application.NewApplication(coordinatorClient)
	var captureClient *upstream.Client
	var searchClient *upstream.Client

	if cfg.captureURL != nil {
		captureClient = upstream.NewClientWithStreamTimeout(*cfg.captureURL, cfg.upstreamTimeout, cfg.streamTimeout)
	}

	if cfg.searchURL != nil {
		searchClient = upstream.NewClient(*cfg.searchURL, cfg.upstreamTimeout)
	}

	gateway.http = &http.Server{
		Handler:           api.NewRouterWithServices(gateway.ready.Load, app, captureClient, searchClient, logger),
		ReadHeaderTimeout: serverReadHeaderTimeout,
		ReadTimeout:       serverReadTimeout,
		IdleTimeout:       serverIdleTimeout,
		MaxHeaderBytes:    serverMaxHeaderBytes,
	}
	return gateway
}

func (g *gatewayServer) serve(ctx context.Context, listener net.Listener) error {
	defer listener.Close()

	stopped := make(chan error, 1)
	g.ready.Store(true)
	defer g.ready.Store(false)

	go func() { stopped <- g.http.Serve(listener) }()

	select {
	case err := <-stopped:
		return fmt.Errorf("HTTP listener stopped unexpectedly: %w", err)
	case <-ctx.Done():
		g.ready.Store(false)
	}

	shutdownCtx, cancel := context.WithTimeout(context.Background(), g.shutdownTimeout)
	defer cancel()

	shutdownErr := g.http.Shutdown(shutdownCtx)

	if shutdownErr != nil {
		shutdownErr = errors.Join(shutdownErr, g.http.Close())
	}

	serveErr := <-stopped

	if !errors.Is(serveErr, http.ErrServerClosed) {
		return errors.Join(shutdownErr, fmt.Errorf("serve HTTP: %w", serveErr))
	}

	return shutdownErr
}
