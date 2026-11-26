package domain

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestApply_CrawlCompletedWithSuccessfulSeedFinalizes(t *testing.T) {
	archive := Archive{
		ID:       "archive-1",
		Status:   StatusAccepted,
		Decision: DecisionNone,
	}
	event := Event{
		ArchiveID:      "archive-1",
		Type:           EventCrawlCompleted,
		ManifestDigest: "manifest-1",
		SeedSucceeded:  true,
		Captured:       3,
		Failed:         1,
	}

	next, effects := apply(t, archive, event)

	assert.Equal(t, Archive{
		ID:             "archive-1",
		Status:         StatusFinalizing,
		Capture:        CaptureProgress{Captured: 3, Failed: 1},
		Decision:       DecisionNone,
		CrawlTerminal:  true,
		SeedSucceeded:  true,
		ManifestDigest: "manifest-1",
	}, next)
	assert.Nil(t, effects)
}

func TestApply_CrawlCompletedWithFailedSeedDecidesCompensation(t *testing.T) {
	archive := Archive{
		ID:       "archive-1",
		Status:   StatusAccepted,
		Decision: DecisionNone,
	}
	event := Event{
		ArchiveID:      "archive-1",
		Type:           EventCrawlCompleted,
		ManifestDigest: "manifest-1",
		SeedSucceeded:  false,
		Captured:       2,
		Failed:         1,
	}

	next, effects := apply(t, archive, event)

	assert.Equal(t, Archive{
		ID:              "archive-1",
		Status:          StatusCompensating,
		Capture:         CaptureProgress{Captured: 2, Failed: 1},
		Decision:        DecisionCompensate,
		DecisionVersion: 1,
		CrawlTerminal:   true,
		ManifestDigest:  "manifest-1",
	}, next)
	assert.Equal(t, []Effect{{
		Type:            CommandCompensationDecided,
		ArchiveID:       "archive-1",
		DecisionVersion: 1,
		ReasonCode:      "seed-capture-failed",
	}}, effects)
}

func TestApply_CrawlCompletedDuplicateIsIgnored(t *testing.T) {
	archive := Archive{
		ID:             "archive-1",
		Status:         StatusFinalizing,
		Capture:        CaptureProgress{Captured: 2, Failed: 1},
		Decision:       DecisionNone,
		CrawlTerminal:  true,
		SeedSucceeded:  true,
		ManifestDigest: "manifest-1",
	}
	event := Event{
		ArchiveID:      "archive-1",
		Type:           EventCrawlCompleted,
		ManifestDigest: "manifest-1",
		SeedSucceeded:  true,
		Captured:       50,
		Failed:         20,
	}

	assertIgnored(t, archive, event)
}

func TestApply_CrawlCompletedWithDifferentDuplicateManifestIsInvalid(t *testing.T) {
	archive := Archive{
		ID:             "archive-1",
		CrawlTerminal:  true,
		ManifestDigest: "manifest-1",
	}
	event := Event{
		ArchiveID:      "archive-1",
		Type:           EventCrawlCompleted,
		ManifestDigest: "manifest-2",
	}

	assertInvalidEvent(t, archive, event)
}

func TestApply_CrawlCompletedWithoutManifestIsInvalid(t *testing.T) {
	archive := Archive{ID: "archive-1", Decision: DecisionNone}
	event := Event{
		ArchiveID: "archive-1",
		Type:      EventCrawlCompleted,
	}

	assertInvalidEvent(t, archive, event)
}

func TestApply_CrawlCompletedWithNegativeCapturedCountIsInvalid(t *testing.T) {
	archive := Archive{ID: "archive-1", Decision: DecisionNone}
	event := Event{
		ArchiveID:      "archive-1",
		Type:           EventCrawlCompleted,
		ManifestDigest: "manifest-1",
		Captured:       -1,
	}

	assertInvalidEvent(t, archive, event)
}

func TestApply_CrawlCompletedWithNegativeFailedCountIsInvalid(t *testing.T) {
	archive := Archive{ID: "archive-1", Decision: DecisionNone}
	event := Event{
		ArchiveID:      "archive-1",
		Type:           EventCrawlCompleted,
		ManifestDigest: "manifest-1",
		Failed:         -1,
	}

	assertInvalidEvent(t, archive, event)
}

func TestApply_CrawlCompletedAfterDecisionIsIgnored(t *testing.T) {
	archive := Archive{
		ID:              "archive-1",
		Status:          StatusFinalizing,
		Decision:        DecisionPublish,
		DecisionVersion: 1,
	}
	event := Event{
		ArchiveID:      "archive-1",
		Type:           EventCrawlCompleted,
		ManifestDigest: "manifest-1",
		SeedSucceeded:  true,
	}

	assertIgnored(t, archive, event)
}

func TestApply_ArchivePreparedStoresDigests(t *testing.T) {
	archive := Archive{ID: "archive-1", Decision: DecisionNone}
	event := Event{
		ArchiveID:      "archive-1",
		Type:           EventArchivePrepared,
		ManifestDigest: "manifest-1",
		PackageDigest:  "package-1",
	}

	next, effects := apply(t, archive, event)

	assert.Equal(t, Archive{
		ID:                     "archive-1",
		Decision:               DecisionNone,
		ManifestDigest:         "",
		PreparedManifestDigest: "manifest-1",
		PackageDigest:          "package-1",
	}, next)
	assert.Nil(t, effects)
}

func TestApply_ArchivePreparedWithoutPackageDigestIsInvalid(t *testing.T) {
	archive := Archive{ID: "archive-1", Decision: DecisionNone}
	event := Event{
		ArchiveID:      "archive-1",
		Type:           EventArchivePrepared,
		ManifestDigest: "manifest-1",
	}

	assertInvalidEvent(t, archive, event)
}

func TestApply_ArchivePreparedWithoutManifestDigestIsInvalid(t *testing.T) {
	archive := Archive{ID: "archive-1", Decision: DecisionNone}
	event := Event{
		ArchiveID:     "archive-1",
		Type:          EventArchivePrepared,
		PackageDigest: "package-1",
	}

	assertInvalidEvent(t, archive, event)
}

func TestApply_ArchivePreparedDuplicateIsIgnored(t *testing.T) {
	archive := Archive{
		ID:                     "archive-1",
		Decision:               DecisionNone,
		PreparedManifestDigest: "manifest-1",
		PackageDigest:          "package-1",
	}
	event := Event{
		ArchiveID:      "archive-1",
		Type:           EventArchivePrepared,
		ManifestDigest: "manifest-1",
		PackageDigest:  "package-1",
	}

	assertIgnored(t, archive, event)
}

func TestApply_ArchivePreparedWithDifferentPackageDigestIsInvalid(t *testing.T) {
	archive := Archive{
		ID:                     "archive-1",
		Decision:               DecisionNone,
		PreparedManifestDigest: "manifest-1",
		PackageDigest:          "package-1",
	}
	event := Event{
		ArchiveID:      "archive-1",
		Type:           EventArchivePrepared,
		ManifestDigest: "manifest-1",
		PackageDigest:  "package-2",
	}

	assertInvalidEvent(t, archive, event)
}

func TestApply_ArchivePreparedWithDifferentManifestDigestIsInvalid(t *testing.T) {
	archive := Archive{
		ID:                     "archive-1",
		Decision:               DecisionNone,
		PreparedManifestDigest: "manifest-1",
		PackageDigest:          "package-1",
	}
	event := Event{
		ArchiveID:      "archive-1",
		Type:           EventArchivePrepared,
		ManifestDigest: "manifest-2",
		PackageDigest:  "package-1",
	}

	assertInvalidEvent(t, archive, event)
}

func TestApply_ArchivePreparedAfterDecisionIsIgnored(t *testing.T) {
	archive := Archive{
		ID:       "archive-1",
		Decision: DecisionCompensate,
	}
	event := Event{
		ArchiveID:      "archive-1",
		Type:           EventArchivePrepared,
		ManifestDigest: "manifest-1",
		PackageDigest:  "package-1",
	}

	assertIgnored(t, archive, event)
}

func TestApply_ArchivePreparedAfterSuccessfulCrawlDecidesPublication(t *testing.T) {
	archive := Archive{
		ID:             "archive-1",
		Status:         StatusFinalizing,
		Decision:       DecisionNone,
		CrawlTerminal:  true,
		SeedSucceeded:  true,
		ManifestDigest: "manifest-1",
	}
	event := Event{
		ArchiveID:      "archive-1",
		Type:           EventArchivePrepared,
		ManifestDigest: "manifest-1",
		PackageDigest:  "package-1",
	}

	next, effects := apply(t, archive, event)

	assert.Equal(t, Archive{
		ID:                     "archive-1",
		Status:                 StatusFinalizing,
		Decision:               DecisionPublish,
		DecisionVersion:        1,
		CrawlTerminal:          true,
		SeedSucceeded:          true,
		ManifestDigest:         "manifest-1",
		PreparedManifestDigest: "manifest-1",
		PackageDigest:          "package-1",
	}, next)
	assert.Equal(t, []Effect{{
		Type:            CommandPublicationDecided,
		ArchiveID:       "archive-1",
		DecisionVersion: 1,
		PackageDigest:   "package-1",
	}}, effects)
}

func TestApply_ArchivePreparedAfterCrawlWithDifferentManifestIsInvalid(t *testing.T) {
	archive := Archive{
		ID:             "archive-1",
		Decision:       DecisionNone,
		CrawlTerminal:  true,
		SeedSucceeded:  true,
		ManifestDigest: "manifest-1",
	}
	event := Event{
		ArchiveID:      "archive-1",
		Type:           EventArchivePrepared,
		ManifestDigest: "manifest-2",
		PackageDigest:  "package-1",
	}

	assertInvalidEvent(t, archive, event)
}

func TestApply_CrawlCompletedAfterPreparedPackageDecidesPublication(t *testing.T) {
	archive := Archive{
		ID:                     "archive-1",
		Status:                 StatusAccepted,
		Decision:               DecisionNone,
		PreparedManifestDigest: "manifest-1",
		PackageDigest:          "package-1",
	}
	event := Event{
		ArchiveID:      "archive-1",
		Type:           EventCrawlCompleted,
		ManifestDigest: "manifest-1",
		SeedSucceeded:  true,
		Captured:       3,
	}

	next, effects := apply(t, archive, event)

	assert.Equal(t, Archive{
		ID:                     "archive-1",
		Status:                 StatusFinalizing,
		Capture:                CaptureProgress{Captured: 3},
		Decision:               DecisionPublish,
		DecisionVersion:        1,
		CrawlTerminal:          true,
		SeedSucceeded:          true,
		ManifestDigest:         "manifest-1",
		PreparedManifestDigest: "manifest-1",
		PackageDigest:          "package-1",
	}, next)
	assert.Equal(t, []Effect{{
		Type:            CommandPublicationDecided,
		ArchiveID:       "archive-1",
		DecisionVersion: 1,
		PackageDigest:   "package-1",
	}}, effects)
}

func TestApply_CrawlCompletedWithDifferentPreparedManifestIsInvalid(t *testing.T) {
	archive := Archive{
		ID:                     "archive-1",
		Decision:               DecisionNone,
		PreparedManifestDigest: "manifest-1",
		PackageDigest:          "package-1",
	}
	event := Event{
		ArchiveID:      "archive-1",
		Type:           EventCrawlCompleted,
		ManifestDigest: "manifest-2",
		SeedSucceeded:  true,
	}

	assertInvalidEvent(t, archive, event)
}

func TestApply_ArchivePublishedCompletesArchiveAndReadiesReplay(t *testing.T) {
	archive := Archive{
		ID:              "archive-1",
		Status:          StatusFinalizing,
		Decision:        DecisionPublish,
		DecisionVersion: 2,
		PackageDigest:   "package-1",
	}
	event := Event{
		ArchiveID:       "archive-1",
		Type:            EventArchivePublished,
		DecisionVersion: 2,
		PackageDigest:   "package-1",
	}

	next, effects := apply(t, archive, event)

	assert.Equal(t, Archive{
		ID:              "archive-1",
		Status:          StatusCompleted,
		Replay:          ReplayProgress{Status: ReplayReady},
		Decision:        DecisionPublish,
		DecisionVersion: 2,
		PackageDigest:   "package-1",
	}, next)
	assert.Nil(t, effects)
}

func TestApply_ArchivePublishedWithCaptureFailuresCompletesWithErrors(t *testing.T) {
	archive := Archive{
		ID:              "archive-1",
		Status:          StatusFinalizing,
		Capture:         CaptureProgress{Captured: 2, Failed: 1},
		Decision:        DecisionPublish,
		DecisionVersion: 2,
		PackageDigest:   "package-1",
	}
	event := Event{
		ArchiveID:       "archive-1",
		Type:            EventArchivePublished,
		DecisionVersion: 2,
		PackageDigest:   "package-1",
	}

	next, effects := apply(t, archive, event)

	assert.Equal(t, Archive{
		ID:              "archive-1",
		Status:          StatusCompletedWithErrors,
		Capture:         CaptureProgress{Captured: 2, Failed: 1},
		Replay:          ReplayProgress{Status: ReplayReady},
		Decision:        DecisionPublish,
		DecisionVersion: 2,
		PackageDigest:   "package-1",
	}, next)
	assert.Nil(t, effects)
}

func TestApply_ArchivePublishedWithoutPublishDecisionIsIgnored(t *testing.T) {
	archive := Archive{
		ID:              "archive-1",
		Status:          StatusFinalizing,
		Decision:        DecisionCompensate,
		DecisionVersion: 2,
		PackageDigest:   "package-1",
	}
	event := Event{
		ArchiveID:       "archive-1",
		Type:            EventArchivePublished,
		DecisionVersion: 2,
		PackageDigest:   "package-1",
	}

	assertIgnored(t, archive, event)
}

func TestApply_ArchivePublishedWithDifferentDecisionVersionIsIgnored(t *testing.T) {
	archive := Archive{
		ID:              "archive-1",
		Status:          StatusFinalizing,
		Decision:        DecisionPublish,
		DecisionVersion: 2,
		PackageDigest:   "package-1",
	}
	event := Event{
		ArchiveID:       "archive-1",
		Type:            EventArchivePublished,
		DecisionVersion: 1,
		PackageDigest:   "package-1",
	}

	assertIgnored(t, archive, event)
}

func TestApply_ArchivePublishedWithDifferentPackageDigestIsIgnored(t *testing.T) {
	archive := Archive{
		ID:              "archive-1",
		Status:          StatusFinalizing,
		Decision:        DecisionPublish,
		DecisionVersion: 2,
		PackageDigest:   "package-1",
	}
	event := Event{
		ArchiveID:       "archive-1",
		Type:            EventArchivePublished,
		DecisionVersion: 2,
		PackageDigest:   "package-2",
	}

	assertIgnored(t, archive, event)
}

func TestApply_DuplicateArchivePublishedForCompletedArchiveIsIgnored(t *testing.T) {
	archive := Archive{
		ID:              "archive-1",
		Status:          StatusCompleted,
		Replay:          ReplayProgress{Status: ReplayNotReady},
		Decision:        DecisionPublish,
		DecisionVersion: 2,
		PackageDigest:   "package-1",
	}
	event := Event{
		ArchiveID:       "archive-1",
		Type:            EventArchivePublished,
		DecisionVersion: 2,
		PackageDigest:   "package-1",
	}

	assertIgnored(t, archive, event)
}

func TestApply_DuplicateArchivePublishedForCompletedWithErrorsArchiveIsIgnored(t *testing.T) {
	archive := Archive{
		ID:              "archive-1",
		Status:          StatusCompletedWithErrors,
		Replay:          ReplayProgress{Status: ReplayNotReady},
		Decision:        DecisionPublish,
		DecisionVersion: 2,
		PackageDigest:   "package-1",
	}
	event := Event{
		ArchiveID:       "archive-1",
		Type:            EventArchivePublished,
		DecisionVersion: 2,
		PackageDigest:   "package-1",
	}

	assertIgnored(t, archive, event)
}

func TestApply_ArchiveCompensatedMarksCaptureCompensated(t *testing.T) {
	archive := Archive{
		ID:              "archive-1",
		Status:          StatusCompensating,
		Decision:        DecisionCompensate,
		DecisionVersion: 3,
	}
	event := Event{
		ArchiveID:       "archive-1",
		Type:            EventArchiveCompensated,
		DecisionVersion: 3,
	}

	next, effects := apply(t, archive, event)

	assert.Equal(t, Archive{
		ID:                 "archive-1",
		Status:             StatusCompensating,
		Decision:           DecisionCompensate,
		DecisionVersion:    3,
		CaptureCompensated: true,
	}, next)
	assert.Nil(t, effects)
}

func TestApply_SearchCompensatedMarksSearchCompensated(t *testing.T) {
	archive := Archive{
		ID:              "archive-1",
		Status:          StatusCompensating,
		Decision:        DecisionCompensate,
		DecisionVersion: 3,
	}
	event := Event{
		ArchiveID:       "archive-1",
		Type:            EventSearchCompensated,
		DecisionVersion: 3,
	}

	next, effects := apply(t, archive, event)

	assert.Equal(t, Archive{
		ID:                "archive-1",
		Status:            StatusCompensating,
		Decision:          DecisionCompensate,
		DecisionVersion:   3,
		SearchCompensated: true,
	}, next)
	assert.Nil(t, effects)
}

func TestApply_CompensationCompletesWhenBothTargetsAreCompensated(t *testing.T) {
	archive := Archive{
		ID:                 "archive-1",
		Status:             StatusCompensating,
		Decision:           DecisionCompensate,
		DecisionVersion:    3,
		CaptureCompensated: true,
	}
	event := Event{
		ArchiveID:       "archive-1",
		Type:            EventSearchCompensated,
		DecisionVersion: 3,
	}

	next, effects := apply(t, archive, event)

	assert.Equal(t, Archive{
		ID:                 "archive-1",
		Status:             StatusFailed,
		Decision:           DecisionCompensate,
		DecisionVersion:    3,
		CaptureCompensated: true,
		SearchCompensated:  true,
	}, next)
	assert.Nil(t, effects)
}

func TestApply_CompensationForDifferentDecisionIsIgnored(t *testing.T) {
	archive := Archive{
		ID:              "archive-1",
		Status:          StatusFinalizing,
		Decision:        DecisionPublish,
		DecisionVersion: 3,
	}
	event := Event{
		ArchiveID:       "archive-1",
		Type:            EventArchiveCompensated,
		DecisionVersion: 3,
	}

	assertIgnored(t, archive, event)
}

func TestApply_CompensationWithDifferentDecisionVersionIsIgnored(t *testing.T) {
	archive := Archive{
		ID:              "archive-1",
		Status:          StatusCompensating,
		Decision:        DecisionCompensate,
		DecisionVersion: 3,
	}
	event := Event{
		ArchiveID:       "archive-1",
		Type:            EventArchiveCompensated,
		DecisionVersion: 2,
	}

	assertIgnored(t, archive, event)
}

func TestApply_SearchReadyMarksSearchReady(t *testing.T) {
	archive := Archive{
		ID:              "archive-1",
		Status:          StatusFinalizing,
		Decision:        DecisionPublish,
		DecisionVersion: 2,
		ManifestDigest:  "manifest-1",
		Search:          SearchProgress{Status: SearchIndexing, Indexed: 2, Expected: 4},
	}
	event := Event{
		ArchiveID:       "archive-1",
		Type:            EventSearchReady,
		DecisionVersion: 2,
		ManifestDigest:  "manifest-1",
	}

	next, effects := apply(t, archive, event)

	assert.Equal(t, Archive{
		ID:              "archive-1",
		Status:          StatusFinalizing,
		Decision:        DecisionPublish,
		DecisionVersion: 2,
		ManifestDigest:  "manifest-1",
		Search:          SearchProgress{Status: SearchReady, Indexed: 2, Expected: 4},
	}, next)
	assert.Nil(t, effects)
}

func TestApply_SearchReadyWithoutPublishDecisionIsIgnored(t *testing.T) {
	archive := Archive{
		ID:              "archive-1",
		Decision:        DecisionCompensate,
		DecisionVersion: 2,
		ManifestDigest:  "manifest-1",
		Search:          SearchProgress{Status: SearchPending},
	}
	event := Event{
		ArchiveID:       "archive-1",
		Type:            EventSearchReady,
		DecisionVersion: 2,
		ManifestDigest:  "manifest-1",
	}

	assertIgnored(t, archive, event)
}

func TestApply_SearchReadyWithDifferentDecisionVersionIsIgnored(t *testing.T) {
	archive := Archive{
		ID:              "archive-1",
		Decision:        DecisionPublish,
		DecisionVersion: 2,
		ManifestDigest:  "manifest-1",
		Search:          SearchProgress{Status: SearchIndexing},
	}
	event := Event{
		ArchiveID:       "archive-1",
		Type:            EventSearchReady,
		DecisionVersion: 1,
		ManifestDigest:  "manifest-1",
	}

	assertIgnored(t, archive, event)
}

func TestApply_SearchReadyWithDifferentManifestIsIgnored(t *testing.T) {
	archive := Archive{
		ID:              "archive-1",
		Decision:        DecisionPublish,
		DecisionVersion: 2,
		ManifestDigest:  "manifest-1",
		Search:          SearchProgress{Status: SearchIndexing},
	}
	event := Event{
		ArchiveID:       "archive-1",
		Type:            EventSearchReady,
		DecisionVersion: 2,
		ManifestDigest:  "manifest-2",
	}

	assertIgnored(t, archive, event)
}

func TestApply_SearchIndexingCompletedTracksProgress(t *testing.T) {
	archive := Archive{
		ID:             "archive-1",
		Status:         StatusFinalizing,
		ManifestDigest: "manifest-1",
		Search:         SearchProgress{Status: SearchPending},
	}
	event := Event{
		ArchiveID:      "archive-1",
		Type:           EventSearchIndexingCompleted,
		ManifestDigest: "manifest-1",
		Indexed:        3,
		Expected:       5,
	}

	next, effects := apply(t, archive, event)

	assert.Equal(t, Archive{
		ID:             "archive-1",
		Status:         StatusFinalizing,
		ManifestDigest: "manifest-1",
		Search:         SearchProgress{Status: SearchIndexing, Indexed: 3, Expected: 5},
	}, next)
	assert.Nil(t, effects)
}

func TestApply_SearchIndexingCompletedPreservesReadyStatus(t *testing.T) {
	archive := Archive{
		ID:             "archive-1",
		ManifestDigest: "manifest-1",
		Search:         SearchProgress{Status: SearchReady, Indexed: 2, Expected: 2},
	}
	event := Event{
		ArchiveID:      "archive-1",
		Type:           EventSearchIndexingCompleted,
		ManifestDigest: "manifest-1",
		Indexed:        4,
		Expected:       4,
	}

	next, effects := apply(t, archive, event)

	assert.Equal(t, Archive{
		ID:             "archive-1",
		ManifestDigest: "manifest-1",
		Search:         SearchProgress{Status: SearchReady, Indexed: 4, Expected: 4},
	}, next)
	assert.Nil(t, effects)
}

func TestApply_SearchIndexingCompletedWithoutManifestIsInvalid(t *testing.T) {
	archive := Archive{ID: "archive-1"}
	event := Event{
		ArchiveID: "archive-1",
		Type:      EventSearchIndexingCompleted,
	}

	assertInvalidEvent(t, archive, event)
}

func TestApply_SearchIndexingCompletedWithNegativeIndexedCountIsInvalid(t *testing.T) {
	archive := Archive{ID: "archive-1"}
	event := Event{
		ArchiveID:      "archive-1",
		Type:           EventSearchIndexingCompleted,
		ManifestDigest: "manifest-1",
		Indexed:        -1,
	}

	assertInvalidEvent(t, archive, event)
}

func TestApply_SearchIndexingCompletedWithNegativeExpectedCountIsInvalid(t *testing.T) {
	archive := Archive{ID: "archive-1"}
	event := Event{
		ArchiveID:      "archive-1",
		Type:           EventSearchIndexingCompleted,
		ManifestDigest: "manifest-1",
		Expected:       -1,
	}

	assertInvalidEvent(t, archive, event)
}

func TestApply_SearchIndexingCompletedWithDifferentManifestIsInvalid(t *testing.T) {
	archive := Archive{
		ID:             "archive-1",
		ManifestDigest: "manifest-1",
	}
	event := Event{
		ArchiveID:      "archive-1",
		Type:           EventSearchIndexingCompleted,
		ManifestDigest: "manifest-2",
	}

	assertInvalidEvent(t, archive, event)
}

func TestApply_EventForDifferentArchiveIsInvalid(t *testing.T) {
	archive := Archive{ID: "archive-1", Status: StatusAccepted}
	event := Event{
		ArchiveID: "archive-2",
		Type:      EventCrawlCompleted,
	}

	assertInvalidEvent(t, archive, event)
}

func TestApply_UnknownEventIsInvalid(t *testing.T) {
	archive := Archive{ID: "archive-1", Status: StatusAccepted}
	event := Event{
		ArchiveID: "archive-1",
		Type:      "unknown",
	}

	assertInvalidEvent(t, archive, event)
}

func apply(t *testing.T, archive Archive, event Event) (Archive, []Effect) {
	t.Helper()

	next, effects, err := Apply(archive, event)
	require.NoError(t, err)

	return next, effects
}

func assertIgnored(t *testing.T, archive Archive, event Event) {
	t.Helper()

	next, effects := apply(t, archive, event)

	assert.Equal(t, archive, next)
	assert.Nil(t, effects)
}

func assertInvalidEvent(t *testing.T, archive Archive, event Event) {
	t.Helper()

	next, effects, err := Apply(archive, event)

	require.ErrorIs(t, err, ErrInvalidEvent)
	assert.Equal(t, archive, next)
	assert.Nil(t, effects)
}
