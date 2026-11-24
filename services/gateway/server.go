package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"net/url"
	"sync/atomic"
	"time"

	"github.com/lemuel-manske/castellani/services/gateway/api"
	"github.com/lemuel-manske/castellani/services/gateway/assembly"
	"github.com/lemuel-manske/castellani/services/gateway/clients/capture"
	"github.com/lemuel-manske/castellani/services/gateway/clients/coordinator"
	"github.com/lemuel-manske/castellani/services/gateway/clients/search"
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
	coordinatorURL, err := url.Parse(cfg.coordinatorURL)

	if err != nil {
		logger.Error(
			"invalid coordinator URL",
			"url",
			cfg.coordinatorURL,
			"error",
			err,
		)
	}

	captureURL, err := url.Parse(cfg.captureURL)

	if err != nil {
		logger.Error(
			"invalid capture URL",
			"url",
			cfg.captureURL,
			"error",
			err,
		)
	}

	loginURL, err := url.Parse(cfg.loginURL)

	if err != nil {
		logger.Error(
			"invalid capture login URL",
			"url",
			cfg.loginURL,
			"error",
			err,
		)
	}

	searchURL, err := url.Parse(cfg.searchURL)

	if err != nil {
		logger.Error(
			"invalid search URL",
			"url",
			cfg.searchURL,
			"error",
			err,
		)
	}

	coordinatorClient := coordinator.NewClient(*coordinatorURL, cfg.upstreamTimeout)
	captureClient := capture.NewClient(
		*captureURL,
		cfg.upstreamTimeout,
		cfg.streamTimeout,
	)
	loginClient := capture.NewClient(
		*loginURL,
		cfg.upstreamTimeout,
		cfg.streamTimeout,
	)
	searchClient := search.NewClient(*searchURL, cfg.upstreamTimeout)

	app := assembly.NewApplication(
		coordinatorClient,
		captureClient,
		loginClient,
		searchClient,
	)

	gateway := &GatewayServer{
		shutdownTimeout: cfg.shutdownTimeout,
	}

	gateway.http = &http.Server{
		Handler: api.NewRouter(
			gateway.ready.Load,
			app,
			*loginURL,
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
