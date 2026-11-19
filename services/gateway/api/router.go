// Package api defines the public HTTP transport layer of the Gateway.
package api

import (
	sharedhttp "github.com/lemuel-manske/castellani/libs/httpx"
	"crypto/rand"
	"encoding/hex"
	"log/slog"
	"net/http"

	"github.com/go-chi/chi/v5"
	archiveapi "github.com/lemuel-manske/unnamed/services/gateway/api/archive"
	searchapi "github.com/lemuel-manske/unnamed/services/gateway/api/search"
	sessionapi "github.com/lemuel-manske/unnamed/services/gateway/api/session"
	"github.com/lemuel-manske/unnamed/services/gateway/application"
	"github.com/lemuel-manske/unnamed/services/gateway/internal/httpx"
	"github.com/lemuel-manske/unnamed/services/gateway/internal/upstream"
)

const (
	healthLivePath = "/health/live"
	healthReadyPath = "/health/ready"
	requestIDHeader = "X-Request-ID"
	healthMediaType = "text/plain; charset=utf-8"
	healthResponse = "ok\n"
)

func NewRouter(ready func() bool, app application.Application, logger *slog.Logger) http.Handler {
	return NewRouterWithServices(ready, app, nil, nil, logger)
}

func NewRouterWithServices(
	ready func() bool,
	app application.Application,
	capture *upstream.Client,
	search *upstream.Client,
	logger *slog.Logger,
) http.Handler {
	router := chi.NewRouter()
	router.Use(requestID)
	router.Use(recoverPanics(logger))

	router.Get(healthLivePath, func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", healthMediaType)
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(healthResponse))
	})
	router.Get(healthReadyPath, func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", healthMediaType)

		if !ready() {
			http.Error(w, "unavailable", http.StatusServiceUnavailable)
			return
		}
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(healthResponse))
	})

	archives := archiveapi.NewHandler(app)
	router.Post(httpx.ArchivesPath, archives.Create)
	router.Get(httpx.ArchivePath, archives.Status)

	if capture != nil {
		metadata := archiveapi.NewMetadataHandler(capture)
		wacz := archiveapi.NewWACZHandler(capture)
		sessions := sessionapi.NewHandler(capture)

		router.Get(archiveapi.PagesPath, metadata.Pages)
		router.Get(archiveapi.SnapshotPath, metadata.Snapshot)
		router.Get(archiveapi.WACZPath, wacz.Get)
		router.Head(archiveapi.WACZPath, wacz.Head)

		router.Post(sessionapi.Path, sessions.Create)
		router.Get(sessionapi.ResourcePath, sessions.Get)
		router.Put(sessionapi.ResourcePath, sessions.Update)
	}

	if search != nil {
		searchHandler := searchapi.NewHandler(search)
		router.Get(searchapi.Path, searchHandler.Search)
	}

	router.NotFound(func(w http.ResponseWriter, r *http.Request) {
		responseProblem := sharedhttp.NewProblem(
			r,
			http.StatusNotFound,
			"not-found",
			"Not Found",
			"The requested resource does not exist.",
		)
		sharedhttp.WriteProblem(w, responseProblem)
	})
	router.MethodNotAllowed(func(w http.ResponseWriter, r *http.Request) {
		responseProblem := sharedhttp.NewProblem(
			r,
			http.StatusMethodNotAllowed,
			"method-not-allowed",
			"Method Not Allowed",
			"The method is not supported for this resource.",
		)
		sharedhttp.WriteProblem(w, responseProblem)
	})
	return router
}

func requestID(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var random [16]byte

		if _, err := rand.Read(random[:]); err != nil {
			responseProblem := sharedhttp.NewProblem(
				r,
				http.StatusInternalServerError,
				"internal",
				"Internal Server Error",
				"Unable to create a request identifier.",
			)
			sharedhttp.WriteProblem(w, responseProblem)
			return
		}
		w.Header().Set(requestIDHeader, hex.EncodeToString(random[:]))
		next.ServeHTTP(w, r)
	})
}

func recoverPanics(logger *slog.Logger) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			defer func() {

				if value := recover(); value != nil {
					logger.Error("HTTP handler panic", "path", r.URL.Path)
					responseProblem := sharedhttp.NewProblem(
						r,
						http.StatusInternalServerError,
						"internal",
						"Internal Server Error",
						"Request handling failed.",
					)
					sharedhttp.WriteProblem(w, responseProblem)
				}
			}()
			next.ServeHTTP(w, r)
		})
	}
}
