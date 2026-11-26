package domain

import "errors"

const (
	DecisionCompensate = "COMPENSATE"
	DecisionPublish    = "PUBLISH"

	EventArchiveCompensated      = "ArchiveCompensated"
	EventArchivePrepared         = "ArchivePrepared"
	EventArchivePublished        = "ArchivePublished"
	EventCrawlCompleted          = "CrawlCompleted"
	EventSearchCompensated       = "SearchCompensated"
	EventSearchIndexingCompleted = "SearchIndexingCompleted"
	EventSearchReady             = "SearchReady"

	CommandCompensationDecided = "ArchiveCompensationDecided"
	CommandPublicationDecided  = "ArchivePublicationDecided"
)

var ErrInvalidEvent = errors.New("inconsistent archive event")

type Event struct {
	MessageID       string
	ArchiveID       string
	Type            string
	ManifestDigest  string
	PackageDigest   string
	DecisionVersion int
	SeedSucceeded   bool
	Captured        int
	Failed          int
	Indexed         int
	Expected        int
}

type Effect struct {
	Type            string
	ArchiveID       string
	DecisionVersion int
	PackageDigest   string
	ReasonCode      string
}

func Apply(archive Archive, event Event) (Archive, []Effect, error) {
	if archive.ID != event.ArchiveID {
		return archive, nil, ErrInvalidEvent
	}

	next := archive

	switch event.Type {
	case EventCrawlCompleted:
		if archive.CrawlTerminal {
			if archive.ManifestDigest != event.ManifestDigest {
				return archive, nil, ErrInvalidEvent
			}

			return archive, nil, nil
		}

		if event.ManifestDigest == "" || event.Captured < 0 || event.Failed < 0 {
			return archive, nil, ErrInvalidEvent
		}

		if archive.Decision != DecisionNone {
			return archive, nil, nil
		}

		next.CrawlTerminal = true
		next.SeedSucceeded = event.SeedSucceeded
		next.ManifestDigest = event.ManifestDigest
		next.Capture.Captured = event.Captured
		next.Capture.Failed = event.Failed
		next.Capture.Pending = 0
		next.Status = StatusFinalizing

	case EventArchivePrepared:
		if event.PackageDigest == "" || event.ManifestDigest == "" {
			return archive, nil, ErrInvalidEvent
		}

		if archive.PackageDigest != "" {
			if archive.PackageDigest != event.PackageDigest || archive.PreparedManifestDigest != event.ManifestDigest {
				return archive, nil, ErrInvalidEvent
			}

			return archive, nil, nil
		}

		if archive.Decision != DecisionNone {
			return archive, nil, nil
		}

		next.PackageDigest = event.PackageDigest
		next.PreparedManifestDigest = event.ManifestDigest

	case EventArchivePublished:
		if archive.Decision != DecisionPublish {
			return archive, nil, nil
		}

		if event.DecisionVersion != archive.DecisionVersion || event.PackageDigest != archive.PackageDigest {
			return archive, nil, nil
		}

		if archive.Status == StatusCompleted || archive.Status == StatusCompletedWithErrors {
			return archive, nil, nil
		}

		next.Replay.Status = ReplayReady

		if next.Capture.Failed > 0 {
			next.Status = StatusCompletedWithErrors
		} else {
			next.Status = StatusCompleted
		}

	case EventArchiveCompensated, EventSearchCompensated:
		if archive.Decision != DecisionCompensate || event.DecisionVersion != archive.DecisionVersion {
			return archive, nil, nil
		}

		if event.Type == EventArchiveCompensated {
			next.CaptureCompensated = true
		} else {
			next.SearchCompensated = true
		}

		if next.CaptureCompensated && next.SearchCompensated {
			next.Status = StatusFailed
		}

	case EventSearchReady:
		if archive.Decision != DecisionPublish || event.DecisionVersion != archive.DecisionVersion {
			return archive, nil, nil
		}

		if event.ManifestDigest != archive.ManifestDigest {
			return archive, nil, nil
		}

		next.Search.Status = SearchReady

	case EventSearchIndexingCompleted:
		if event.ManifestDigest == "" || event.Indexed < 0 || event.Expected < 0 {
			return archive, nil, ErrInvalidEvent
		}

		if archive.ManifestDigest != "" && archive.ManifestDigest != event.ManifestDigest {
			return archive, nil, ErrInvalidEvent
		}

		next.Search.Indexed = event.Indexed
		next.Search.Expected = event.Expected

		if archive.Search.Status != SearchReady {
			next.Search.Status = SearchIndexing
		}

	default:
		return archive, nil, ErrInvalidEvent
	}

	if next.Decision == DecisionNone && next.CrawlTerminal {
		if !next.SeedSucceeded {
			next.Decision = DecisionCompensate
			next.DecisionVersion++
			next.Status = StatusCompensating

			return next, []Effect{{
				Type:            CommandCompensationDecided,
				ArchiveID:       archive.ID,
				DecisionVersion: next.DecisionVersion,
				ReasonCode:      "seed-capture-failed",
			}}, nil
		}

		if next.PackageDigest != "" {
			if next.PreparedManifestDigest != next.ManifestDigest {
				return archive, nil, ErrInvalidEvent
			}

			next.Decision = DecisionPublish
			next.DecisionVersion++
			next.Status = StatusFinalizing

			return next, []Effect{{
				Type:            CommandPublicationDecided,
				ArchiveID:       archive.ID,
				DecisionVersion: next.DecisionVersion,
				PackageDigest:   next.PackageDigest,
			}}, nil
		}
	}

	return next, nil, nil
}
