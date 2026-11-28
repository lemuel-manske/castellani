package infra

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	awscredentials "github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	dynamodbtypes "github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	s3types "github.com/aws/aws-sdk-go-v2/service/s3/types"
)

const (
	cleanupRequestTimeout = 30 * time.Second
)

var (
	cleanupHTTPClient = &http.Client{
		Timeout: cleanupRequestTimeout,
	}

	archiveTables = []string{
		coordinatorArchivesTable,
		coordinatorOutboxTable,
		coordinatorInboxTable,
		captureRunsTable,
		captureFrontierTable,
		captureOutboxTable,
		captureSnapshotsTable,
		searchIndexingLedgerTable,
		searchPublicationLedgerTable,
		searchOutboxTable,
		searchManifestLedgerTable,
	}
)

func cleanupTestArchives(ctx context.Context, d Dependencies, runID string) error {
	config, err := awsConfig()

	if err != nil {
		return fmt.Errorf("load aws config: %w", err)
	}

	dynamoClient := dynamodb.NewFromConfig(config, func(options *dynamodb.Options) {
		options.BaseEndpoint = aws.String(d.MiniStack.BaseURL())
	})

	s3Client := s3.NewFromConfig(config, func(options *s3.Options) {
		options.BaseEndpoint = aws.String(d.MiniStack.BaseURL())
		options.UsePathStyle = true
	})

	archiveIDs, submissionKeys, err := listTestArchives(ctx, dynamoClient, runID)

	if err != nil {
		return err
	}

	if len(archiveIDs) == 0 && len(submissionKeys) == 0 {
		return nil
	}

	var errs []error

	errs = append(errs, deleteTestSubmissions(ctx, dynamoClient, submissionKeys))

	for _, archiveID := range archiveIDs {
		errs = append(errs, deleteArchiveRows(ctx, dynamoClient, archiveID))
		errs = append(errs, deleteArchiveObjects(ctx, s3Client, archiveID))
		errs = append(errs, deleteArchiveDocuments(ctx, d.OpenSearch, archiveID))
	}

	return errors.Join(errs...)
}

func listTestArchives(
	ctx context.Context,
	client *dynamodb.Client,
	runID string,
) ([]string, []string, error) {
	paginator := dynamodb.NewScanPaginator(client, &dynamodb.ScanInput{
		TableName:        aws.String(coordinatorSubmissionsTable),
		FilterExpression: aws.String("begins_with(idempotencyKey, :prefix)"),
		ExpressionAttributeValues: map[string]dynamodbtypes.AttributeValue{
			":prefix": &dynamodbtypes.AttributeValueMemberS{Value: runID + "-"},
		},
		ProjectionExpression: aws.String("idempotencyKey, archiveId"),
	})

	var (
		archiveIDs     []string
		submissionKeys []string
	)

	for paginator.HasMorePages() {
		page, err := paginator.NextPage(ctx)

		if err != nil {
			return nil, nil, fmt.Errorf("list test submissions: %w", err)
		}

		for _, item := range page.Items {
			key := stringValue(item["idempotencyKey"])

			if key == "" {
				continue
			}

			submissionKeys = append(submissionKeys, key)

			if archiveID := stringValue(item["archiveId"]); archiveID != "" {
				archiveIDs = append(archiveIDs, archiveID)
			}
		}
	}

	return archiveIDs, submissionKeys, nil
}

func deleteTestSubmissions(
	ctx context.Context,
	client *dynamodb.Client,
	keys []string,
) error {
	if len(keys) == 0 {
		return nil
	}

	items := make([]map[string]dynamodbtypes.AttributeValue, 0, len(keys))

	for _, key := range keys {
		items = append(items, map[string]dynamodbtypes.AttributeValue{
			"idempotencyKey": &dynamodbtypes.AttributeValueMemberS{Value: key},
		})
	}

	return batchDelete(ctx, client, coordinatorSubmissionsTable, items)
}

func deleteArchiveRows(
	ctx context.Context,
	client *dynamodb.Client,
	archiveID string,
) error {
	var errs []error

	values := map[string]dynamodbtypes.AttributeValue{
		":archiveId": &dynamodbtypes.AttributeValueMemberS{Value: archiveID},
	}

	for _, table := range archiveTables {
		errs = append(errs, deleteTableItems(
			ctx,
			client,
			table,
			"archiveId = :archiveId",
			values,
		))
	}

	return errors.Join(errs...)
}

func deleteTableItems(
	ctx context.Context,
	client *dynamodb.Client,
	table string,
	filter string,
	values map[string]dynamodbtypes.AttributeValue,
) error {
	keyNames, err := tableKeyNames(ctx, client, table)

	if err != nil {
		return err
	}

	paginator := dynamodb.NewScanPaginator(client, &dynamodb.ScanInput{
		TableName:                 aws.String(table),
		FilterExpression:          aws.String(filter),
		ExpressionAttributeValues: values,
	})

	var keys []map[string]dynamodbtypes.AttributeValue

	for paginator.HasMorePages() {
		page, err := paginator.NextPage(ctx)

		if err != nil {
			return fmt.Errorf("scan %s: %w", table, err)
		}

		for _, item := range page.Items {
			key := make(map[string]dynamodbtypes.AttributeValue, len(keyNames))

			for _, name := range keyNames {
				key[name] = item[name]
			}

			keys = append(keys, key)
		}
	}

	return batchDelete(ctx, client, table, keys)
}

func tableKeyNames(
	ctx context.Context,
	client *dynamodb.Client,
	table string,
) ([]string, error) {
	description, err := client.DescribeTable(ctx, &dynamodb.DescribeTableInput{
		TableName: aws.String(table),
	})

	if err != nil {
		return nil, fmt.Errorf("describe %s: %w", table, err)
	}

	names := make([]string, 0, len(description.Table.KeySchema))

	for _, key := range description.Table.KeySchema {
		names = append(names, aws.ToString(key.AttributeName))
	}

	return names, nil
}

func batchDelete(
	ctx context.Context,
	client *dynamodb.Client,
	table string,
	keys []map[string]dynamodbtypes.AttributeValue,
) error {
	const batchSize = 25

	for len(keys) > 0 {
		size := min(len(keys), batchSize)

		requests := make([]dynamodbtypes.WriteRequest, 0, size)

		for _, key := range keys[:size] {
			requests = append(requests, dynamodbtypes.WriteRequest{
				DeleteRequest: &dynamodbtypes.DeleteRequest{
					Key: key,
				},
			})
		}

		keys = keys[size:]

		for attempts := 0; len(requests) > 0; attempts++ {
			if attempts >= 10 {
				return fmt.Errorf("delete items from %s: too many unprocessed batches", table)
			}

			output, err := client.BatchWriteItem(ctx, &dynamodb.BatchWriteItemInput{
				RequestItems: map[string][]dynamodbtypes.WriteRequest{
					table: requests,
				},
			})

			if err != nil {
				return fmt.Errorf("delete items from %s: %w", table, err)
			}

			requests = output.UnprocessedItems[table]
		}
	}

	return nil
}

func deleteArchiveObjects(ctx context.Context, client *s3.Client, archiveID string) error {
	quoted := url.QueryEscape(archiveID)

	targets := []struct {
		bucket string
		prefix string
	}{
		{archiveArtifactsBucket, "capture-staging/" + quoted + "/"},
		{archiveArtifactsBucket, "packages/" + quoted + "/"},
		{archiveManifestsBucket, "manifests/" + quoted + "/"},
	}

	var errs []error

	for _, target := range targets {
		errs = append(errs, deleteS3Prefix(ctx, client, target.bucket, target.prefix))
	}

	return errors.Join(errs...)
}

func deleteS3Prefix(ctx context.Context, client *s3.Client, bucket string, prefix string) error {
	paginator := s3.NewListObjectsV2Paginator(client, &s3.ListObjectsV2Input{
		Bucket: aws.String(bucket),
		Prefix: aws.String(prefix),
	})

	var objects []s3types.ObjectIdentifier

	for paginator.HasMorePages() {
		page, err := paginator.NextPage(ctx)

		if err != nil {
			return fmt.Errorf("list %s/%s: %w", bucket, prefix, err)
		}

		for _, object := range page.Contents {
			objects = append(objects, s3types.ObjectIdentifier{
				Key: object.Key,
			})
		}
	}

	const batchSize = 1000

	for len(objects) > 0 {
		size := min(len(objects), batchSize)

		output, err := client.DeleteObjects(ctx, &s3.DeleteObjectsInput{
			Bucket: aws.String(bucket),
			Delete: &s3types.Delete{
				Objects: objects[:size],
				Quiet:   aws.Bool(true),
			},
		})

		if err != nil {
			return fmt.Errorf("delete %s/%s: %w", bucket, prefix, err)
		}

		if len(output.Errors) > 0 {
			return fmt.Errorf("delete %s/%s: %v", bucket, prefix, output.Errors)
		}

		objects = objects[size:]
	}

	return nil
}

func deleteArchiveDocuments(ctx context.Context, search Service, archiveID string) error {
	body := strings.NewReader(fmt.Sprintf(`{"query":{"term":{"archiveId":%q}}}`, archiveID))

	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		search.URL("/"+searchIndexName+"/_delete_by_query?refresh=true"),
		body,
	)

	if err != nil {
		return err
	}

	request.Header.Set("Content-Type", "application/json")

	response, err := cleanupHTTPClient.Do(request)

	if err != nil {
		return fmt.Errorf("delete search documents for %s: %w", archiveID, err)
	}
	defer response.Body.Close()

	if response.StatusCode != http.StatusOK && response.StatusCode != http.StatusNotFound {
		data, _ := io.ReadAll(io.LimitReader(response.Body, 4096))

		return fmt.Errorf(
			"delete search documents for %s: status %d: %s",
			archiveID,
			response.StatusCode,
			strings.TrimSpace(string(data)),
		)
	}

	return nil
}

func awsConfig() (aws.Config, error) {
	return awsconfig.LoadDefaultConfig(
		context.Background(),
		awsconfig.WithRegion(awsRegion),
		awsconfig.WithCredentialsProvider(
			awscredentials.NewStaticCredentialsProvider(
				awsAccessKeyID,
				awsSecretAccessKey,
				"",
			),
		),
	)
}

func stringValue(value dynamodbtypes.AttributeValue) string {
	if attribute, ok := value.(*dynamodbtypes.AttributeValueMemberS); ok {
		return attribute.Value
	}

	return ""
}
