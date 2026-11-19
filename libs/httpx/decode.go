package httpx

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime"
	"net/http"
)

const MaxJSONRequestBytes = 64 << 10

var (
	ErrContentType = errors.New("Content-Type must be application/json")
	ErrInvalidJSON = errors.New("expected a valid JSON object")
	ErrExtraJSON   = errors.New("expected exactly one JSON object")
)

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
