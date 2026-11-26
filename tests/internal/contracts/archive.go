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
