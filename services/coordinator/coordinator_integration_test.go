//go:build integration

package main

import (
	"encoding/json"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/lemuel-manske/castellani/libs/httpx"
	archiveapi "github.com/lemuel-manske/castellani/services/coordinator/api/archive"
	"github.com/lemuel-manske/castellani/services/coordinator/common"
	"github.com/lemuel-manske/castellani/services/coordinator/contracts"
	"github.com/lemuel-manske/castellani/services/coordinator/domain"
	"github.com/lemuel-manske/castellani/services/coordinator/internal/testutil"
	"github.com/lemuel-manske/castellani/services/coordinator/topology"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestCoordinator_SubmittingArchiveStoresItAndPublishesStartCrawl(t *testing.T) {
	infrastructure := testutil.NewInfrastructure(t)
	deliveries := testutil.Subscribe(
		t,
		infrastructure.RabbitMQ,
		topology.EventsExchange,
		contracts.StartCrawlType,
	)
	coordinatorURL := startCoordinator(t)

	response := testutil.Post(
		t,
		coordinatorURL,
		common.ArchivesPath,
		`{"seedUrl":"https://example.org/","maxDepth":2,"maxPages":5}`,
		map[string]string{
			httpx.HeaderContentType:    "application/json",
			httpx.HeaderIdempotencyKey: "archive-key-0001",
		},
	)

	require.Equal(
		t,
		http.StatusAccepted,
		response.Status,
	)

	var accepted archiveapi.AcceptedResponse
	require.NoError(t, json.Unmarshal([]byte(response.Body), &accepted))

	require.NotEmpty(t, accepted.ArchiveID)

	assert.Equal(
		t,
		accepted.StatusURL,
		response.Header.Get(httpx.HeaderLocation),
	)

	assert.Equal(
		t,
		archiveapi.AcceptedResponse{
			ArchiveID: accepted.ArchiveID,
			Status:    domain.StatusAccepted,
			StatusURL: common.ArchivePathPrefix + accepted.ArchiveID,
		},
		accepted,
	)

	statusResponse := testutil.Get(
		t,
		coordinatorURL,
		accepted.StatusURL,
	)
	require.Equal(
		t,
		http.StatusOK,
		statusResponse.Status,
	)

	var status archiveapi.ArchiveResponse
	require.NoError(t, json.Unmarshal([]byte(statusResponse.Body), &status))

	assert.Equal(
		t,
		accepted.ArchiveID,
		status.ArchiveID,
	)
	assert.Equal(
		t,
		domain.StatusAccepted,
		status.Status,
	)

	delivery := testutil.Receive(t, deliveries)
	require.NotEmpty(t, delivery.MessageId)

	var startCrawl contracts.StartCrawlEnvelope
	require.NoError(t, json.Unmarshal(delivery.Body, &startCrawl))

	_, err := time.Parse(time.RFC3339Nano, startCrawl.OccurredAt)
	require.NoError(t, err)

	assert.Equal(
		t,
		topology.EventsExchange,
		delivery.Exchange,
	)

	assert.Equal(
		t,
		contracts.StartCrawlType,
		delivery.RoutingKey,
	)

	assert.Equal(
		t,
		contracts.StartCrawlEnvelope{
			MessageID:     delivery.MessageId,
			CorrelationID: accepted.ArchiveID,
			Type:          contracts.StartCrawlType,
			Version:       contracts.EnvelopeVersion,
			OccurredAt:    startCrawl.OccurredAt,
			Payload: contracts.StartCrawlPayload{
				ArchiveID: accepted.ArchiveID,
				SeedURL:   "https://example.org/",
				MaxDepth:  2,
				MaxPages:  5,
			},
		},
		startCrawl,
	)
}

func TestCoordinator_RepeatedSubmissionReturnsOriginalArchiveAndPublishesOnce(t *testing.T) {
	infrastructure := testutil.NewInfrastructure(t)
	deliveries := testutil.Subscribe(
		t,
		infrastructure.RabbitMQ,
		topology.EventsExchange,
		contracts.StartCrawlType,
	)

	coordinatorURL := startCoordinator(t)

	requestBody := `{"seedUrl":"https://example.org/","maxDepth":2,"maxPages":5}`

	headers := map[string]string{
		httpx.HeaderContentType:    "application/json",
		httpx.HeaderIdempotencyKey: "archive-key-0002",
	}

	firstResponse := testutil.Post(
		t,
		coordinatorURL,
		common.ArchivesPath,
		requestBody,
		headers,
	)
	require.Equal(
		t,
		http.StatusAccepted,
		firstResponse.Status,
	)

	var firstAccepted archiveapi.AcceptedResponse
	require.NoError(t, json.Unmarshal([]byte(firstResponse.Body), &firstAccepted))

	secondResponse := testutil.Post(
		t,
		coordinatorURL,
		common.ArchivesPath,
		requestBody,
		headers,
	)
	require.Equal(
		t,
		http.StatusAccepted,
		secondResponse.Status,
	)

	var secondAccepted archiveapi.AcceptedResponse
	require.NoError(t, json.Unmarshal([]byte(secondResponse.Body), &secondAccepted))

	assert.Equal(
		t,
		firstAccepted,
		secondAccepted,
	)

	delivery := testutil.Receive(t, deliveries)

	var startCrawl contracts.StartCrawlEnvelope
	require.NoError(t, json.Unmarshal(delivery.Body, &startCrawl))

	assert.Equal(
		t,
		firstAccepted.ArchiveID,
		startCrawl.CorrelationID,
	)
	assert.Equal(
		t,
		contracts.StartCrawlType,
		delivery.RoutingKey,
	)

	testutil.RequireNoMessage(t, deliveries)
}

func TestCoordinator_ReusingIdempotencyKeyForDifferentSubmissionConflicts(t *testing.T) {
	infrastructure := testutil.NewInfrastructure(t)
	deliveries := testutil.Subscribe(
		t,
		infrastructure.RabbitMQ,
		topology.EventsExchange,
		contracts.StartCrawlType,
	)

	coordinatorURL := startCoordinator(t)

	headers := map[string]string{
		httpx.HeaderContentType:    "application/json",
		httpx.HeaderIdempotencyKey: "archive-key-0003",
	}

	firstResponse := testutil.Post(
		t,
		coordinatorURL,
		common.ArchivesPath,
		`{"seedUrl":"https://example.org/","maxDepth":2,"maxPages":5}`,
		headers,
	)
	require.Equal(
		t,
		http.StatusAccepted,
		firstResponse.Status,
	)

	var accepted archiveapi.AcceptedResponse
	require.NoError(t, json.Unmarshal([]byte(firstResponse.Body), &accepted))

	conflictResponse := testutil.Post(
		t,
		coordinatorURL,
		common.ArchivesPath,
		`{"seedUrl":"https://example.net/","maxDepth":2,"maxPages":5}`,
		headers,
	)
	require.Equal(
		t,
		http.StatusConflict,
		conflictResponse.Status,
	)

	delivery := testutil.Receive(t, deliveries)

	var startCrawl contracts.StartCrawlEnvelope
	require.NoError(t, json.Unmarshal(delivery.Body, &startCrawl))

	assert.Equal(
		t,
		accepted.ArchiveID,
		startCrawl.CorrelationID,
	)

	testutil.RequireNoMessage(t, deliveries)
}

func TestCoordinator_DuplicateFailedSeedEventEmitsOneCompensation(t *testing.T) {
	infrastructure := testutil.NewInfrastructure(t)
	compensations := testutil.Subscribe(
		t,
		infrastructure.RabbitMQ,
		topology.EventsExchange,
		domain.CommandCompensationDecided,
	)
	coordinatorURL := startCoordinator(t)

	response := testutil.Post(
		t,
		coordinatorURL,
		common.ArchivesPath,
		`{"seedUrl":"https://example.org/","maxDepth":2,"maxPages":5}`,
		map[string]string{
			httpx.HeaderContentType:    "application/json",
			httpx.HeaderIdempotencyKey: "archive-key-0004",
		},
	)
	require.Equal(
		t,
		http.StatusAccepted,
		response.Status,
	)

	var accepted archiveapi.AcceptedResponse
	require.NoError(t, json.Unmarshal([]byte(response.Body), &accepted))

	crawlCompleted := contracts.Envelope[map[string]any]{
		MessageID:     "crawl-completed-0001",
		CorrelationID: accepted.ArchiveID,
		Type:          domain.EventCrawlCompleted,
		Version:       contracts.EnvelopeVersion,
		OccurredAt:    time.Now().UTC().Format(time.RFC3339Nano),
		Payload: map[string]any{
			"archiveId": accepted.ArchiveID,
			"manifest": map[string]any{
				"bucket":    "coordinator-test-artifacts",
				"key":       "archives/" + accepted.ArchiveID + "/manifest.json",
				"sha256":    strings.Repeat("a", 64),
				"sizeBytes": 1,
			},
			"manifestDigest": "manifest-1",
			"seedSucceeded":  false,
			"capturedCount":  2,
			"failedCount":    1,
		},
	}

	testutil.Publish(
		t,
		infrastructure.RabbitMQ,
		topology.EventsExchange,
		domain.EventCrawlCompleted,
		crawlCompleted,
	)
	testutil.Publish(
		t,
		infrastructure.RabbitMQ,
		topology.EventsExchange,
		domain.EventCrawlCompleted,
		crawlCompleted,
	)

	status := waitForArchiveStatus(
		t,
		coordinatorURL,
		accepted.StatusURL,
		domain.StatusCompensating,
	)

	assert.Equal(
		t,
		domain.DecisionCompensate,
		status.Decision,
	)

	compensation := testutil.Receive(t, compensations)

	var command contracts.ArchiveCompensationDecidedEnvelope
	require.NoError(t, json.Unmarshal(compensation.Body, &command))

	assert.Equal(
		t,
		domain.CommandCompensationDecided,
		command.Type,
	)

	assert.Equal(
		t,
		accepted.ArchiveID,
		command.Payload.ArchiveID,
	)

	assert.Equal(
		t,
		1,
		command.Payload.DecisionVersion,
	)

	assert.Equal(
		t,
		"seed-capture-failed",
		command.Payload.ReasonCode,
	)

	testutil.RequireNoMessage(t, compensations)
}

func TestCoordinator_SuccessfulPublicationCompletesArchive(t *testing.T) {
	infrastructure := testutil.NewInfrastructure(t)
	publicationDecisions := testutil.Subscribe(
		t,
		infrastructure.RabbitMQ,
		topology.EventsExchange,
		domain.CommandPublicationDecided,
	)
	coordinatorURL := startCoordinator(t)

	response := testutil.Post(
		t,
		coordinatorURL,
		common.ArchivesPath,
		`{"seedUrl":"https://example.org/","maxDepth":2,"maxPages":5}`,
		map[string]string{
			httpx.HeaderContentType:    "application/json",
			httpx.HeaderIdempotencyKey: "archive-key-0005",
		},
	)
	require.Equal(
		t,
		http.StatusAccepted,
		response.Status,
	)

	var accepted archiveapi.AcceptedResponse
	require.NoError(t, json.Unmarshal([]byte(response.Body), &accepted))

	manifestDigest := "manifest-1"
	packageDigest := "package-1"

	prepared := contracts.Envelope[map[string]any]{
		MessageID:     "archive-prepared-0001",
		CorrelationID: accepted.ArchiveID,
		Type:          domain.EventArchivePrepared,
		Version:       contracts.EnvelopeVersion,
		OccurredAt:    time.Now().UTC().Format(time.RFC3339Nano),
		Payload: map[string]any{
			"archiveId": accepted.ArchiveID,
			"package": map[string]any{
				"bucket":    "coordinator-test-artifacts",
				"key":       "archives/" + accepted.ArchiveID + "/package.wacz",
				"sha256":    strings.Repeat("a", 64),
				"sizeBytes": 1,
			},
			"packageDigest":  packageDigest,
			"manifestDigest": manifestDigest,
		},
	}
	testutil.Publish(
		t,
		infrastructure.RabbitMQ,
		topology.EventsExchange,
		domain.EventArchivePrepared,
		prepared,
	)

	crawlCompleted := contracts.Envelope[map[string]any]{
		MessageID:     "crawl-completed-0002",
		CorrelationID: accepted.ArchiveID,
		Type:          domain.EventCrawlCompleted,
		Version:       contracts.EnvelopeVersion,
		OccurredAt:    time.Now().UTC().Format(time.RFC3339Nano),
		Payload: map[string]any{
			"archiveId": accepted.ArchiveID,
			"manifest": map[string]any{
				"bucket":    "coordinator-test-artifacts",
				"key":       "archives/" + accepted.ArchiveID + "/manifest.json",
				"sha256":    strings.Repeat("a", 64),
				"sizeBytes": 1,
			},
			"manifestDigest": manifestDigest,
			"seedSucceeded":  true,
			"capturedCount":  3,
			"failedCount":    0,
		},
	}
	testutil.Publish(
		t,
		infrastructure.RabbitMQ,
		topology.EventsExchange,
		domain.EventCrawlCompleted,
		crawlCompleted,
	)

	publicationDecision := testutil.Receive(t, publicationDecisions)

	var command contracts.ArchivePublicationDecidedEnvelope
	require.NoError(t, json.Unmarshal(publicationDecision.Body, &command))

	assert.Equal(
		t,
		domain.CommandPublicationDecided,
		command.Type,
	)

	assert.Equal(
		t,
		accepted.ArchiveID,
		command.Payload.ArchiveID,
	)

	assert.Equal(
		t,
		1,
		command.Payload.DecisionVersion,
	)

	assert.Equal(
		t,
		packageDigest,
		command.Payload.PackageDigest,
	)

	published := contracts.Envelope[map[string]any]{
		MessageID:     "archive-published-0001",
		CorrelationID: accepted.ArchiveID,
		Type:          domain.EventArchivePublished,
		Version:       contracts.EnvelopeVersion,
		OccurredAt:    time.Now().UTC().Format(time.RFC3339Nano),
		Payload: map[string]any{
			"archiveId":       accepted.ArchiveID,
			"decisionVersion": 1,
			"packageDigest":   packageDigest,
		},
	}
	testutil.Publish(
		t,
		infrastructure.RabbitMQ,
		topology.EventsExchange,
		domain.EventArchivePublished,
		published,
	)

	status := waitForArchiveStatus(
		t,
		coordinatorURL,
		accepted.StatusURL,
		domain.StatusCompleted,
	)

	assert.Equal(
		t,
		accepted.ArchiveID,
		status.ArchiveID,
	)

	assert.Equal(
		t,
		domain.DecisionPublish,
		status.Decision,
	)

	assert.Equal(
		t,
		domain.ReplayReady,
		status.Replay.Status,
	)
}
