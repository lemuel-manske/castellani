package dynamodb

import (
	"encoding/json"
	"fmt"
	"strconv"
	"time"

	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/lemuel-manske/castellani/services/coordinator/contracts"
	"github.com/lemuel-manske/castellani/services/coordinator/domain"
)

const archiveTimestampLayout = "2006-01-02T15:04:05.000000000Z07:00"

func stringValue(value types.AttributeValue) string {
	attribute, ok := value.(*types.AttributeValueMemberS)

	if !ok {
		return ""
	}

	return attribute.Value
}

func numberValue(value types.AttributeValue) int {
	attribute, ok := value.(*types.AttributeValueMemberN)

	if !ok {
		return 0
	}

	number, _ := strconv.Atoi(attribute.Value)

	return number
}

func boolValue(value types.AttributeValue) bool {
	attribute, ok := value.(*types.AttributeValueMemberBOOL)

	if !ok {
		return false
	}

	return attribute.Value
}

func archiveFromItem(id string, item map[string]types.AttributeValue) domain.Archive {
	updatedAt, _ := time.Parse(archiveTimestampLayout, stringValue(item["updatedAt"]))
	decision := stringValue(item["decision"])

	if decision == "" {
		decision = domain.DecisionNone
	}

	return domain.Archive{
		ID:                     id,
		Status:                 stringValue(item["status"]),
		Revision:               numberValue(item["revision"]),
		UpdatedAt:              updatedAt,
		Decision:               decision,
		DecisionVersion:        numberValue(item["decisionVersion"]),
		CrawlTerminal:          boolValue(item["crawlTerminal"]),
		SeedSucceeded:          boolValue(item["seedSucceeded"]),
		ManifestDigest:         stringValue(item["manifestDigest"]),
		PreparedManifestDigest: stringValue(item["preparedDigest"]),
		PackageDigest:          stringValue(item["packageDigest"]),
		CaptureCompensated:     boolValue(item["captureCompensated"]),
		SearchCompensated:      boolValue(item["searchCompensated"]),
		Capture: domain.CaptureProgress{
			Captured: numberValue(item["captured"]),
			Failed:   numberValue(item["failed"]),
			Pending:  numberValue(item["pending"]),
		},
		Replay: domain.ReplayProgress{
			Status: stringValue(item["replayStatus"]),
		},
		Search: domain.SearchProgress{
			Status:   stringValue(item["searchStatus"]),
			Indexed:  numberValue(item["indexed"]),
			Expected: numberValue(item["expected"]),
		},
	}
}

func encodeEffect(
	messageID string,
	effect domain.Effect,
	now time.Time,
) ([]byte, error) {
	var payload any = contracts.ArchiveCompensationDecidedPayload{
		ArchiveID:       effect.ArchiveID,
		DecisionVersion: effect.DecisionVersion,
		ReasonCode:      effect.ReasonCode,
	}

	if effect.Type == domain.CommandPublicationDecided {
		payload = contracts.ArchivePublicationDecidedPayload{
			ArchiveID:       effect.ArchiveID,
			DecisionVersion: effect.DecisionVersion,
			PackageDigest:   effect.PackageDigest,
		}
	}

	envelope, err := json.Marshal(contracts.Envelope[any]{
		MessageID:     messageID,
		CorrelationID: effect.ArchiveID,
		Type:          effect.Type,
		Version:       contracts.EnvelopeVersion,
		OccurredAt:    now.Format(time.RFC3339Nano),
		Payload:       payload,
	})

	if err != nil {
		return nil, fmt.Errorf(
			"encode %s: %w",
			effect.Type,
			err,
		)
	}

	return envelope, nil
}
