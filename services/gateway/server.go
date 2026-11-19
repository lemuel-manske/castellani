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
	"github.com/lemuel-manske/unnamed/services/gateway/assembly"
	"github.com/lemuel-manske/unnamed/services/gateway/clients/capture"
	"github.com/lemuel-manske/unnamed/services/gateway/clients/coordinator"
	"github.com/lemuel-manske/unnamed/services/gateway/clients/search"
	"github.com/lemuel-manske/unnamed/services/gateway/internal/upstream"
)

const (
	serverReadHeaderTimeout = 5 * time.Second
	serverReadTimeout       = 15 * time.Second
	serverIdleTimeout       = 60 * time.Second
	serverMaxHeaderBytes    = 32 << 10
)

type GatewayServer struct {
	http            *http.Server
	ready           atomic.Bool
	shutdownTimeout time.Duration
}

func NewGatewayServer(cfg Config, logger *slog.Logger) *GatewayServer {
	coordinatorClient := coordinator.NewClient(*cfg.coordinatorURL, cfg.upstreamTimeout)

	var captureClient *capture.Client
	var searchClient *search.Client

	if cfg.captureURL != nil {
		captureClient = capture.NewClient(
			*cfg.captureURL,
			cfg.upstreamTimeout,
			cfg.streamTimeout,
		)
	}

	if cfg.searchURL != nil {
		searchClient = search.NewClient(*cfg.searchURL, cfg.upstreamTimeout)
	}

	app := assembly.NewApplication(
		coordinatorClient,
		captureClient,
		searchClient,
	)

	// Legacy API clients remain until the HTTP handlers migrate to the application.
	var legacyCapture *upstream.Client
	var legacySearch *upstream.Client

	if cfg.captureURL != nil {
		legacyCapture = upstream.NewClientWithStreamTimeout(
			*cfg.captureURL,
			cfg.upstreamTimeout,
			cfg.streamTimeout,
		)
	}

	if cfg.searchURL != nil {
		legacySearch = upstream.NewClient(*cfg.searchURL, cfg.upstreamTimeout)
	}

	gateway := &GatewayServer{shutdownTimeout: cfg.shutdownTimeout}
	gateway.http = &http.Server{
		Handler: api.NewRouterWithServices(
			gateway.ready.Load,
			app,
			legacyCapture,
			legacySearch,
			logger,
		),
		ReadHeaderTimeout: serverReadHeaderTimeout,
		ReadTimeout:       serverReadTimeout,
		IdleTimeout:       serverIdleTimeout,
		MaxHeaderBytes:    serverMaxHeaderBytes,
	}
	return gateway
}

func (g *GatewayServer) Serve(ctx context.Context, listener net.Listener) error {
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
