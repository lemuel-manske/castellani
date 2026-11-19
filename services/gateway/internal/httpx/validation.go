package httpx

import (
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	shared "github.com/lemuel-manske/castellani/libs/httpx"
)

const (
	MaxJSONRequestBytes = shared.MaxJSONRequestBytes
	DefaultLimit        = 25
	MaxLimit            = 100
	MaxQueryLength      = 500
)

var (
	ErrContentType = shared.ErrContentType
	ErrInvalidJSON = shared.ErrInvalidJSON
	ErrExtraJSON   = shared.ErrExtraJSON
)

func DecodeJSON(w http.ResponseWriter, r *http.Request, destination any) error {
	return shared.DecodeJSON(w, r, destination)
}

func DecodeJSONBytes(w http.ResponseWriter, r *http.Request, destination any) ([]byte, error) {
	return shared.DecodeJSONBytes(w, r, destination)
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
	return shared.ValidateIdempotencyKey(key)
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
