package httpx

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime"
	"net/http"
	"strings"
)

const (
	MaxJSONRequestBytes      = 64 << 10
	minIdempotencyKeyLength  = 8
	maxIdempotencyKeyLength  = 200
)

var (
	ErrContentType = errors.New("Content-Type must be application/json")
	ErrInvalidJSON = errors.New("expected a valid JSON object")
	ErrExtraJSON   = errors.New("expected exactly one JSON object")
)

func ValidateIdempotencyKey(key string) bool {
	validLength := len(key) >= minIdempotencyKeyLength && len(key) <= maxIdempotencyKeyLength
	cleanWhitespace := strings.TrimSpace(key) == key
	noControlCharacters := !strings.ContainsAny(key, "\r\n\x00")

	return validLength && cleanWhitespace && noControlCharacters
}

// DecodeJSONBytes decodes one strict JSON value and returns the original bytes.
// Callers that forward the request can preserve its original representation.
func DecodeJSONBytes(w http.ResponseWriter, r *http.Request, destination any) ([]byte, error) {
	mediaType, _, err := mime.ParseMediaType(r.Header.Get(HeaderContentType))

	if err != nil || mediaType != MediaTypeJSON {
		return nil, ErrContentType
	}

	data, err := io.ReadAll(http.MaxBytesReader(w, r.Body, MaxJSONRequestBytes))

	if err != nil {
		return nil, fmt.Errorf("read JSON request: %w", err)
	}

	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()

	if err := decoder.Decode(destination); err != nil {
		return nil, fmt.Errorf("%w: %v", ErrInvalidJSON, err)
	}

	var extra any

	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		return nil, ErrExtraJSON
	}

	return data, nil
}

func DecodeJSON(w http.ResponseWriter, r *http.Request, destination any) error {
	_, err := DecodeJSONBytes(w, r, destination)
	return err
}
