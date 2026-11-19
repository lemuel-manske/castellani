// Package api defines the public HTTP transport layer of the Gateway.
package api

import (
	"crypto/rand"
	"encoding/hex"
	"log/slog"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/lemuel-manske/castellani/libs/httpx"
	archiveapi "github.com/lemuel-manske/unnamed/services/gateway/api/archive"
	searchapi "github.com/lemuel-manske/unnamed/services/gateway/api/search"
	sessionapi "github.com/lemuel-manske/unnamed/services/gateway/api/session"
	"github.com/lemuel-manske/unnamed/services/gateway/application"
	"github.com/lemuel-manske/unnamed/services/gateway/common"
)

const (
	healthMediaType = "text/plain; charset=utf-8"
	healthResponse  = "ok\n"
)

func NewRouter(
	ready func() bool,
	app application.Application,
	logger *slog.Logger,
) http.Handler {
	router := chi.NewRouter()

	router.Use(requestID)
	router.Use(recoverPanics(logger))

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

	metadata := archiveapi.NewMetadataHandler(app)
	wacz := archiveapi.NewWACZHandler(app)
	sessions := sessionapi.NewHandler(app)
	search := searchapi.NewHandler(app)

	router.Get(common.PagesPath, metadata.Pages)
	router.Get(common.SnapshotPath, metadata.Snapshot)
	router.Get(common.WACZPath, wacz.Get)
	router.Head(common.WACZPath, wacz.Head)
	router.Post(common.SessionsPath, sessions.Create)
	router.Get(common.SessionPath, sessions.Get)
	router.Put(common.SessionPath, sessions.Update)
	router.Get(common.SearchPath, search.Search)

	router.NotFound(func(w http.ResponseWriter, r *http.Request) {
		responseProblem := httpx.NewProblem(
			r,
			http.StatusNotFound,
			"not-found",
			"Not Found",
			"The requested resource does not exist.",
		)
		httpx.WriteProblem(w, responseProblem)
	})
	router.MethodNotAllowed(func(w http.ResponseWriter, r *http.Request) {
		responseProblem := httpx.NewProblem(
			r,
			http.StatusMethodNotAllowed,
			"method-not-allowed",
			"Method Not Allowed",
			"The method is not supported for this resource.",
		)
		httpx.WriteProblem(w, responseProblem)
	})
	return router
}

func requestID(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var random [16]byte

		if _, err := rand.Read(random[:]); err != nil {
			responseProblem := httpx.NewProblem(
				r,
				http.StatusInternalServerError,
				"internal",
				"Internal Server Error",
				"Unable to create a request identifier.",
			)
			httpx.WriteProblem(w, responseProblem)
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
					responseProblem := httpx.NewProblem(
						r,
						http.StatusInternalServerError,
						"internal",
						"Internal Server Error",
						"Request handling failed.",
					)
					httpx.WriteProblem(w, responseProblem)
				}
			}()
			next.ServeHTTP(w, r)
		})
	}
}
