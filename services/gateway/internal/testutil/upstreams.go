// Package testutil provides in-process upstream servers and HTTP helpers for Gateway tests.
package testutil

import (
	"io"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"github.com/lemuel-manske/castellani/libs/httpx"
)

type Response struct {
	Status  int
	Body    string
	Headers map[string]string
	Delay   time.Duration
}

func OK(body string) Response {
	return Response{
		Status: http.StatusOK,
		Body:   body,
	}
}

type Option func(*upstreamConfig)

type upstreamConfig struct {
	coordinator []Response
	capture     []Response
	login       []Response
	search      []Response
}

func Coordinator(responses ...Response) Option {
	return func(config *upstreamConfig) {
		config.coordinator = responses
	}
}

func Capture(responses ...Response) Option {
	return func(config *upstreamConfig) {
		config.capture = responses
	}
}

func Login(responses ...Response) Option {
	return func(config *upstreamConfig) {
		config.login = responses
	}
}

func Search(responses ...Response) Option {
	return func(config *upstreamConfig) {
		config.search = responses
	}
}

type Upstreams struct {
	Coordinator Service
	Capture     Service
	Login       Service
	Search      Service
}

type Service struct {
	URL string

	record *recorder
}

type Request struct {
	Method  string
	Path    string
	Headers http.Header
	Body    string
}

func (s Service) Requests() []Request {
	return s.record.snapshot()
}

func StartUpstreams(t *testing.T, options ...Option) Upstreams {
	config := upstreamConfig{}

	for _, option := range options {
		option(&config)
	}

	return Upstreams{
		Coordinator: startService(t, config.coordinator),
		Capture:     startService(t, config.capture),
		Login:       startService(t, config.login),
		Search:      startService(t, config.search),
	}
}

func startService(t *testing.T, responses []Response) Service {
	record := &recorder{}

	sequence := &responseSequence{
		responses: responses,
	}

	server := httptest.NewServer(
		http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			body, err := io.ReadAll(r.Body)

			if err != nil {
				http.Error(
					w,
					err.Error(),
					http.StatusBadRequest,
				)

				return
			}

			record.add(
				Request{
					Method:  r.Method,
					Path:    r.URL.Path,
					Headers: r.Header.Clone(),
					Body:    string(body),
				},
			)

			response, ok := sequence.next()

			if !ok {
				httpx.WriteProblem(
					w,
					httpx.NewProblem(
						r,
						http.StatusInternalServerError,
						"unexpected-upstream-request",
						"Unexpected Upstream Request",
						"No response was configured for this request.",
					),
				)

				return
			}

			time.Sleep(response.Delay)

			for name, value := range response.Headers {
				w.Header().Set(name, value)
			}

			status := response.Status

			if status == 0 {
				status = http.StatusOK
			}

			w.WriteHeader(status)

			_, _ = io.WriteString(w, response.Body)
		}),
	)
	t.Cleanup(server.Close)

	return Service{
		URL:    server.URL,
		record: record,
	}
}

type recorder struct {
	mu       sync.Mutex
	requests []Request
}

func (r *recorder) add(request Request) {
	r.mu.Lock()
	defer r.mu.Unlock()

	r.requests = append(r.requests, request)
}

func (r *recorder) snapshot() []Request {
	r.mu.Lock()
	defer r.mu.Unlock()

	return append([]Request(nil), r.requests...)
}

type responseSequence struct {
	mu        sync.Mutex
	responses []Response
	index     int
}

func (s *responseSequence) next() (Response, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.index >= len(s.responses) {
		return Response{}, false
	}

	response := s.responses[s.index]
	s.index++

	return response, true
}
