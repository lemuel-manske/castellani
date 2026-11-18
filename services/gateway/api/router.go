// Package api defines the public HTTP transport layer of the Gateway.
package api

import (
	"crypto/rand"
	"encoding/hex"
	"log/slog"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/lemuel-manske/unnamed/services/gateway/application"
	archiveapi "github.com/lemuel-manske/unnamed/services/gateway/api/archive"
	"github.com/lemuel-manske/unnamed/services/gateway/internal/httpx"
)

func NewRouter(ready func() bool, app application.Application, logger *slog.Logger) http.Handler {
	router := chi.NewRouter()
	router.Use(requestID)
	router.Use(recoverPanics(logger))

	router.Get("/health/live", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "text/plain; charset=utf-8")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok\n"))
	})
	router.Get("/health/ready", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "text/plain; charset=utf-8")
		if !ready() {
			http.Error(w, "unavailable", http.StatusServiceUnavailable)
			return
		}
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok\n"))
	})

	archives := archiveapi.NewHandler(app)
	router.Post("/archives", archives.Create)
	router.Get("/archives/{archiveId}", archives.Status)

	router.NotFound(func(w http.ResponseWriter, r *http.Request) {
		httpx.WriteProblem(w, r, http.StatusNotFound, "not-found", "Not Found", "The requested resource does not exist.")
	})
	router.MethodNotAllowed(func(w http.ResponseWriter, r *http.Request) {
		httpx.WriteProblem(w, r, http.StatusMethodNotAllowed, "method-not-allowed", "Method Not Allowed", "The method is not supported for this resource.")
	})
	return router
}

func requestID(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var random [16]byte
		if _, err := rand.Read(random[:]); err != nil {
			httpx.WriteProblem(w, r, http.StatusInternalServerError, "internal", "Internal Server Error", "Unable to create a request identifier.")
			return
		}
		w.Header().Set("X-Request-ID", hex.EncodeToString(random[:]))
		next.ServeHTTP(w, r)
	})
}

func recoverPanics(logger *slog.Logger) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			defer func() {
				if value := recover(); value != nil {
					logger.Error("HTTP handler panic", "path", r.URL.Path)
					httpx.WriteProblem(w, r, http.StatusInternalServerError, "internal", "Internal Server Error", "Request handling failed.")
				}
			}()
			next.ServeHTTP(w, r)
		})
	}
}
