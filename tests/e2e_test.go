//go:build e2e

package tests_test

import (
	"context"
	"net/http"
	"testing"

	"github.com/lemuel-manske/castellani/tests/internal/infra"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestDependencies_AllReachable(t *testing.T) {
	ctx := context.Background()
	deps := infra.Start(t)

	miniStackStatus, miniStackErr := deps.MiniStack.HealthStatus(ctx)
	require.NoError(t, miniStackErr)

	rabbitMQStatus, rabbitMQErr := deps.RabbitMQ.HealthStatus(ctx)
	require.NoError(t, rabbitMQErr)

	openSearchStatus, openSearchErr := deps.OpenSearch.HealthStatus(ctx)
	require.NoError(t, openSearchErr)

	assert.Equal(t, http.StatusOK, miniStackStatus)
	assert.Equal(t, http.StatusOK, rabbitMQStatus)
	assert.Equal(t, http.StatusOK, openSearchStatus)
}
