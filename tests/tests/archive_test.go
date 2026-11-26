package tests

import (
	"net/http"
	"testing"

	"github.com/lemuel-manske/castellani/tests/internal/contracts"
	"github.com/lemuel-manske/castellani/tests/internal/fixtures"
	"github.com/lemuel-manske/castellani/tests/internal/infra"
	"github.com/lemuel-manske/castellani/tests/internal/testutil"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestArchiveSubmission_AcceptsValidRequest(t *testing.T) {
	services := infra.Start(t)

	response := testutil.Post(
		t,
		services.Gateway.BaseURL(),
		"/archives",
		fixtures.ValidArchive,
		map[string]string{
			testutil.HeaderContentType:    testutil.ContentTypeJSON,
			testutil.HeaderIdempotencyKey: fixtures.AcceptedIdempotencyKey,
		},
	)

	require.Equal(
		t,
		http.StatusAccepted,
		response.Status,
	)

	accepted := testutil.Decode[contracts.ArchiveAccepted](t, response)

	assert.NotEmpty(t, accepted.ArchiveID)
	assert.Equal(
		t,
		contracts.ArchiveAccepted{
			ArchiveID: accepted.ArchiveID,
			Status:    "ACCEPTED",
			StatusURL: "/archives/" + accepted.ArchiveID,
		},
		accepted,
	)
	assert.Equal(
		t,
		accepted.StatusURL,
		response.Header.Get(testutil.HeaderLocation),
	)
}
