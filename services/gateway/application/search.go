package application

import (
	"context"
)

func (a Application) Search(ctx context.Context, query SearchQuery) (SearchResults, error) {
	if err := query.Validate(); err != nil {
		return SearchResults{}, err
	}

	if a.search == nil {
		return SearchResults{}, ErrDependencyUnavailable
	}

	return a.search.Search(ctx, query)
}
