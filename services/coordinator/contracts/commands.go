package contracts

type ArchiveCompensationDecidedPayload struct {
	ArchiveID       string `json:"archiveId"`
	DecisionVersion int    `json:"decisionVersion"`
	ReasonCode      string `json:"reasonCode"`
}

type ArchiveCompensationDecidedEnvelope = Envelope[ArchiveCompensationDecidedPayload]

type ArchivePublicationDecidedPayload struct {
	ArchiveID       string `json:"archiveId"`
	DecisionVersion int    `json:"decisionVersion"`
	PackageDigest   string `json:"packageDigest"`
}

type ArchivePublicationDecidedEnvelope = Envelope[ArchivePublicationDecidedPayload]
