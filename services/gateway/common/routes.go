package common

const (
	ArchivesPath = "/archives"
	ArchivePath  = "/archives/{archiveId}"
	PagesPath    = "/archives/{archiveId}/pages"
	SnapshotPath = "/archives/{archiveId}/snapshots/{snapshotId}"
	WACZPath     = "/archives/{archiveId}/wacz"
	SessionsPath = "/sessions"
	SessionPath  = "/sessions/{sessionId}"
	SearchPath   = "/search"
	HealthLivePath  = "/health/live"
	HealthReadyPath = "/health/ready"

	ArchivePathPrefix  = "/archives/"
	SessionPathPrefix  = "/sessions/"
	SnapshotPathSegment = "/snapshots/"
	PagesPathSuffix     = "/pages"
	WACZPathSuffix      = "/wacz"

	ArchiveIDParameter  = "archiveId"
	SnapshotIDParameter = "snapshotId"
	SessionIDParameter  = "sessionId"
)
