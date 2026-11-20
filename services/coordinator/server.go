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

	"github.com/lemuel-manske/castellani/services/coordinator/api"
	"github.com/lemuel-manske/castellani/services/coordinator/application"
)

const (
	serverReadHeaderTimeout = 5 * time.Second
	serverReadTimeout       = 15 * time.Second
	serverIdleTimeout       = 60 * time.Second
	serverMaxHeaderBytes    = 32 << 10
)

type CoordinatorServer struct {
	http            *http.Server
	ready           atomic.Bool
	shutdownTimeout time.Duration
}

func NewCoordinatorServer(
	config Config,
	app *application.Application,
	logger *slog.Logger,
) *CoordinatorServer {
	server := &CoordinatorServer{
		shutdownTimeout: config.shutdownTimeout,
	}

	server.http = &http.Server{
		Handler: api.NewRouter(
			server.ready.Load,
			app,
			logger,
		),
		ReadHeaderTimeout: serverReadHeaderTimeout,
		ReadTimeout:       serverReadTimeout,
		IdleTimeout:       serverIdleTimeout,
		MaxHeaderBytes:    serverMaxHeaderBytes,
	}

	return server
}

func (s *CoordinatorServer) Serve(ctx context.Context, listener net.Listener) error {
	defer listener.Close()

	stopped := make(chan error, 1)
	s.ready.Store(true)

	go func() {
		stopped <- s.http.Serve(listener)
	}()

	select {
	case err := <-stopped:
		s.ready.Store(false)

		return fmt.Errorf("HTTP listener stopped unexpectedly: %w", err)
	case <-ctx.Done():
		s.ready.Store(false)
	}

	shutdownCtx, cancel := context.WithTimeout(context.Background(), s.shutdownTimeout)
	defer cancel()

	shutdownErr := s.http.Shutdown(shutdownCtx)

	if shutdownErr != nil {
		shutdownErr = errors.Join(shutdownErr, s.http.Close())
	}

	serveErr := <-stopped

	if !errors.Is(serveErr, http.ErrServerClosed) {
		return errors.Join(shutdownErr, fmt.Errorf("serve HTTP: %w", serveErr))
	}

	return shutdownErr
}
