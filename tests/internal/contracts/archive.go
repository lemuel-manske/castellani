// Package contracts mirrors the public API shapes used by the end-to-end suite.
package contracts

type Problem struct {
	Type     string `json:"type"`
	Title    string `json:"title"`
	Status   int    `json:"status"`
	Detail   string `json:"detail"`
	Instance string `json:"instance"`
}

type ArchiveAccepted struct {
	ArchiveID string `json:"archiveId"`
	Status    string `json:"status"`
	StatusURL string `json:"statusUrl"`
}

type ArchiveStatus struct {
	ArchiveID string          `json:"archiveId"`
	Status    string          `json:"status"`
	Decision  string          `json:"decision"`
	Capture   CaptureProgress `json:"capture"`
	Replay    ReplayProgress  `json:"replay"`
	Search    SearchProgress  `json:"search"`
}

type CaptureProgress struct {
	Captured int `json:"captured"`
	Failed   int `json:"failed"`
	Pending  int `json:"pending"`
}

type ReplayProgress struct {
	Status string `json:"status"`
}

type SearchProgress struct {
	Status   string `json:"status"`
	Indexed  int    `json:"indexed"`
	Expected int    `json:"expected"`
}

type ArchivePages struct {
	Items      []PageOutcome `json:"items"`
	NextCursor *string       `json:"nextCursor"`
}

type PageOutcome struct {
	URL        string `json:"url"`
	Status     string `json:"status"`
	SnapshotID string `json:"snapshotId"`
}

type Snapshot struct {
	ArchiveID  string `json:"archiveId"`
	SnapshotID string `json:"snapshotId"`
	URL        string `json:"url"`
	CapturedAt string `json:"capturedAt"`
}

type SearchResults struct {
	Results    []SearchResult `json:"results"`
	NextCursor *string        `json:"nextCursor"`
}

type SearchResult struct {
	CollectionID string  `json:"collectionId,omitempty"`
	ArchiveID    string  `json:"archiveId"`
	SnapshotID   string  `json:"snapshotId"`
	URL          string  `json:"url"`
	CapturedAt   string  `json:"capturedAt"`
	Title        string  `json:"title,omitempty"`
	Snippet      string  `json:"snippet"`
	Score        float64 `json:"score,omitempty"`
}
