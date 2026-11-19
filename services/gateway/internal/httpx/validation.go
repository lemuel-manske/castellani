package httpx

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
)

const (
	MaxJSONRequestBytes = 64 << 10
	DefaultLimit        = 25
	MaxLimit            = 100
	MaxQueryLength      = 500
)

func DecodeJSON(w http.ResponseWriter, r *http.Request, destination any) error {
	mediaType, _, err := mime.ParseMediaType(r.Header.Get(HeaderContentType))

	if err != nil || mediaType != MediaTypeJSON {
		return errors.New("Content-Type must be application/json")
	}

	data, err := io.ReadAll(http.MaxBytesReader(w, r.Body, MaxJSONRequestBytes))

	if err != nil {
		return fmt.Errorf("read JSON request: %w", err)
	}

	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()

	if err := decoder.Decode(destination); err != nil {
		return fmt.Errorf("decode JSON request: %w", err)
	}

	var extra any

	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		return errors.New("expected exactly one JSON object")
	}

	return nil
}

func ValidatePagination(values url.Values) error {
	limits := values["limit"]

	if len(limits) > 1 {
		return errors.New("limit must be supplied once")
	}

	if len(limits) == 1 {
		value, err := strconv.Atoi(limits[0])

		if err != nil {
			return errors.New("limit must be an integer")
		}

		if value < 1 || value > MaxLimit {
			return errors.New("limit must be between 1 and 100")
		}
	}

	if len(values["cursor"]) > 1 {
		return errors.New("cursor must be supplied once")
	}

	return nil
}

func ValidateID(id string) bool {
	reserved := id == "" || id == "." || id == ".."
	forbidden := strings.ContainsAny(id, "/\\?#")

	return !reserved && !forbidden
}

func ValidateIdempotencyKey(key string) bool {
	validLength := len(key) >= 8 && len(key) <= 200
	cleanWhitespace := strings.TrimSpace(key) == key
	noControl := !strings.ContainsAny(key, "\r\n\x00")

	return validLength && cleanWhitespace && noControl
}

func ValidateTargetURL(raw string) bool {
	target, err := url.Parse(raw)

	if err != nil {
		return false
	}

	scheme := target.Scheme == "http" || target.Scheme == "https"
	authority := target.Hostname() != "" && target.User == nil
	noFragment := target.Fragment == ""

	return scheme && authority && noFragment
}

func ValidateSearch(values url.Values) error {
	allowed := map[string]bool{
		"q": true, "limit": true, "cursor": true, "collectionId": true,
		"archiveId": true, "snapshotId": true, "capturedFrom": true, "capturedTo": true,
	}

	for name, entries := range values {
		if !allowed[name] || len(entries) != 1 {
			return errors.New("unknown or repeated search parameter")
		}
	}

	query := values.Get("q")

	if len(query) == 0 || len(query) > MaxQueryLength || strings.TrimSpace(query) == "" {
		return errors.New("q must contain between 1 and 500 characters")
	}

	if err := ValidatePagination(values); err != nil {
		return err
	}

	for _, name := range []string{"capturedFrom", "capturedTo"} {
		raw := values.Get(name)

		if raw != "" {
			if _, err := time.Parse(time.RFC3339, raw); err != nil {
				return fmt.Errorf("%s must be RFC3339", name)
			}
		}
	}

	from, fromErr := time.Parse(time.RFC3339, values.Get("capturedFrom"))
	to, toErr := time.Parse(time.RFC3339, values.Get("capturedTo"))

	if fromErr == nil && toErr == nil && from.After(to) {
		return errors.New("capturedFrom must not exceed capturedTo")
	}

	return nil
}
