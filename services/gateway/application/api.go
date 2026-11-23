// Package application provides the Gateway's application use cases.
package application

type Application struct {
	coordinator Coordinator
	capture     Capture
	search      Search
}

func NewApplication(
	coordinator Coordinator,
	capture Capture,
	search Search,
) Application {
	return Application{
		coordinator: coordinator,
		capture:     capture,
		search:      search,
	}
}
