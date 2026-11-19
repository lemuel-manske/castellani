package common

const (
	ArchivePath  = "/archives/{archiveId}"
	ArchivesPath = "/archives"
	HealthLivePath  = "/health/live"
	HealthReadyPath = "/health/ready"
	PagesPath    = "/archives/{archiveId}/pages"
	SearchPath   = "/search"
	SessionPath  = "/sessions/{sessionId}"
	SessionsPath = "/sessions"
	SnapshotPath = "/archives/{archiveId}/snapshots/{snapshotId}"
	WACZPath     = "/archives/{archiveId}/wacz"

	ArchivePathPrefix  = "/archives/"
	SessionPathPrefix  = "/sessions/"

	SnapshotPathSegment = "/snapshots/"

	PagesPathSuffix     = "/pages"
	WACZPathSuffix      = "/wacz"

	ArchiveIDParameter  = "archiveId"
	SessionIDParameter  = "sessionId"
	SnapshotIDParameter = "snapshotId"
)
