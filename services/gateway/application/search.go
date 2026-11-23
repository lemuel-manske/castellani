package application

import "context"

func (a Application) Search(ctx context.Context, query SearchQuery) (SearchResults, error) {
	if a.search == nil {
		return SearchResults{}, ErrDependencyUnavailable
	}

	return a.search.Search(ctx, query)
}
