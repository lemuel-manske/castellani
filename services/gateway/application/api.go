// Package application provides the Gateway's application use cases.
package application

type Application struct {
	coordinator Coordinator
	capture     Capture
	login       Login
	search      Search
}

func NewApplication(
	coordinator Coordinator,
	capture Capture,
	login Login,
	search Search,
) Application {
	return Application{
		coordinator: coordinator,
		capture:     capture,
		login:       login,
		search:      search,
	}
}
