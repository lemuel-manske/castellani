package gatewaytest

import "maps"

const CoordinatorURL = "http://coordinator:8080"
const CaptureURL = "http://capture:8080"
const SearchURL = "http://search:8080"

func Environment(overrides map[string]string) func(string) string {
	settings := map[string]string{
		"COORDINATOR_URL": CoordinatorURL,
		"CAPTURE_URL":     CaptureURL,
		"SEARCH_URL":      SearchURL,
	}

	maps.Copy(settings, overrides)

	return func(name string) string {
		return settings[name]
	}
}
