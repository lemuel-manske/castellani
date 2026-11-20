// Package api defines the public HTTP transport layer of the Coordinator.
package api

import (
	"crypto/rand"
	"encoding/hex"
	"log/slog"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/lemuel-manske/castellani/libs/httpx"
	archiveapi "github.com/lemuel-manske/unnamed/services/coordinator/api/archive"
	"github.com/lemuel-manske/unnamed/services/coordinator/application"
	"github.com/lemuel-manske/unnamed/services/coordinator/common"
)

const (
	healthMediaType = "text/plain; charset=utf-8"
	healthResponse  = "ok\n"
)

func NewRouter(
	ready func() bool,
	app *application.Application,
	logger *slog.Logger,
) http.Handler {
	router := chi.NewRouter()

	router.Use(requestID)
	router.Use(recoverPanics(logger))

	router.Use(func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			started := time.Now()

			next.ServeHTTP(w, r)

			logger.Info(
				"HTTP request",
				"request_id",
				r.Header.Get(httpx.HeaderRequestID),
				"method",
				r.Method,
				"path",
				r.URL.Path,
				"duration",
				time.Since(started),
			)
		})
	})

	router.Get(common.HealthLivePath, func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", healthMediaType)
		w.WriteHeader(http.StatusOK)

		_, _ = w.Write([]byte(healthResponse))
	})

	router.Get(common.HealthReadyPath, func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", healthMediaType)

		if !ready() {
			http.Error(
				w,
				"unavailable",
				http.StatusServiceUnavailable,
			)

			return
		}

		w.WriteHeader(http.StatusOK)

		_, _ = w.Write([]byte(healthResponse))
	})

	archives := archiveapi.NewHandler(app)
	router.Post(common.ArchivesPath, archives.Create)
	router.Get(common.ArchivePath, archives.Status)

	router.NotFound(func(w http.ResponseWriter, r *http.Request) {
		httpx.WriteProblem(w, httpx.NewProblem(
			r,
			http.StatusNotFound,
			"not-found",
			"Not Found",
			"The requested resource does not exist.",
		))
	})

	router.MethodNotAllowed(func(w http.ResponseWriter, r *http.Request) {
		httpx.WriteProblem(w, httpx.NewProblem(
			r,
			http.StatusMethodNotAllowed,
			"method-not-allowed",
			"Method Not Allowed",
			"The method is not supported for this resource.",
		))
	})

	return router
}

func requestID(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var random [16]byte

		if _, err := rand.Read(random[:]); err != nil {
			httpx.WriteProblem(w, httpx.NewProblem(
				r,
				http.StatusInternalServerError,
				"internal",
				"Internal Server Error",
				"Unable to create a request identifier.",
			))

			return
		}

		w.Header().Set(httpx.HeaderRequestID, hex.EncodeToString(random[:]))

		next.ServeHTTP(w, r)
	})
}

func recoverPanics(logger *slog.Logger) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			defer func() {
				if value := recover(); value != nil {
					logger.Error(
						"HTTP handler panic",
						"path",
						r.URL.Path,
					)

					httpx.WriteProblem(w, httpx.NewProblem(
						r,
						http.StatusInternalServerError,
						"internal",
						"Internal Server Error",
						"Request handling failed.",
					))
				}
			}()

			next.ServeHTTP(w, r)
		})
	}
}
