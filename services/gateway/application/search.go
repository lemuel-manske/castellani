package application

import (
	"context"
	"encoding/json"
)

func (a Application) Search(ctx context.Context, query SearchQuery) (json.RawMessage, error) {
	if err := query.Validate(); err != nil {
		return nil, err
	}

	if a.search == nil {
		return nil, ErrDependencyUnavailable
	}
	return a.search.Search(ctx, query)
}
