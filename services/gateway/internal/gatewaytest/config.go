package gatewaytest

const CoordinatorURL = "http://coordinator:8080"

// Environment supplies a valid Coordinator origin and applies explicit overrides.
func Environment(overrides map[string]string) func(string) string {
	settings := map[string]string{
		"COORDINATOR_URL": CoordinatorURL,
		"CAPTURE_URL": "http://capture:8080",
		"SEARCH_URL": "http://search:8080",
	}

	for name, value := range overrides {
		settings[name] = value
	}

	return func(name string) string {
		return settings[name]
	}
}
