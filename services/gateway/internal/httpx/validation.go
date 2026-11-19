package httpx

import (
	"errors"
	"fmt"
	"net/url"
	"strconv"
	"strings"
	"time"
)

const (
	DefaultLimit   = 25
	MaxLimit       = 100
	MaxQueryLength = 500
)

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
