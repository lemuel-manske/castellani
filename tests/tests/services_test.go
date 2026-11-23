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

func TestServices_AllReachable(t *testing.T) {
	ctx := context.Background()
	services := infra.Start(t)

	gatewayStatus, gatewayErr := services.Gateway.HealthStatus(ctx)
	require.NoError(t, gatewayErr)

	coordinatorStatus, coordinatorErr := services.Coordinator.HealthStatus(ctx)
	require.NoError(t, coordinatorErr)

	captureStatus, captureErr := services.Capture.HealthStatus(ctx)
	require.NoError(t, captureErr)

	searchStatus, searchErr := services.Search.HealthStatus(ctx)
	require.NoError(t, searchErr)

	assert.Equal(
		t,
		http.StatusOK,
		gatewayStatus,
	)
	assert.Equal(
		t,
		http.StatusOK,
		coordinatorStatus,
	)
	assert.Equal(
		t,
		http.StatusOK,
		captureStatus,
	)
	assert.Equal(
		t,
		http.StatusOK,
		searchStatus,
	)
}
