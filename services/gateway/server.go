package main

import (
	"context"
	"errors"
	"fmt"
	"net"
	"net/http"
	"sync/atomic"
	"time"
)

type gatewayServer struct {
	http            *http.Server
	ready           atomic.Bool
	shutdownTimeout time.Duration
}

func newGatewayServer(cfg config) *gatewayServer {
	gateway := &gatewayServer{shutdownTimeout: cfg.shutdownTimeout}
	gateway.http = &http.Server{
		Handler:           newHandler(gateway.ready.Load),
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       15 * time.Second,
		IdleTimeout:       60 * time.Second,
		MaxHeaderBytes:    32 << 10,
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
		closeErr := g.http.Close()
		shutdownErr = errors.Join(shutdownErr, closeErr)
	}

	serveErr := <-stopped
	if !errors.Is(serveErr, http.ErrServerClosed) {
		return errors.Join(shutdownErr, fmt.Errorf("serve HTTP: %w", serveErr))
	}

	return shutdownErr
}

func newHandler(ready func() bool) http.Handler {
	mux := http.NewServeMux()

	mux.HandleFunc("GET /health/live", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "text/plain; charset=utf-8")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok\n"))
	})

	mux.HandleFunc("GET /health/ready", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "text/plain; charset=utf-8")
		if !ready() {
			http.Error(w, "unavailable", http.StatusServiceUnavailable)
			return
		}
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok\n"))
	})

	return mux
}
