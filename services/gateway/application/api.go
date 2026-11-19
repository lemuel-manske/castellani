// Package application provides the Gateway's application use cases.
package application

type Application struct {
	coordinator Coordinator
	capture     Capture
	search      Search
}

type ValidationError struct {
	Cause error
}

func (e *ValidationError) Error() string { return e.Cause.Error() }

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
