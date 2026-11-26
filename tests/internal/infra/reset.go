package infra

import (
	"context"
	"encoding/json"
	"net/http"
	"net/url"
	"testing"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	awscredentials "github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	dynamodbtypes "github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	s3types "github.com/aws/aws-sdk-go-v2/service/s3/types"
	"github.com/stretchr/testify/require"
)

const resetRequestTimeout = 30 * time.Second

var resetHTTPClient = &http.Client{
	Timeout: resetRequestTimeout,
}

// Reset clears state left behind by a test while keeping the shared stack running.
func (d Dependencies) Reset(t *testing.T) {
	t.Helper()

	ctx, cancel := context.WithTimeout(context.Background(), resetRequestTimeout)
	defer cancel()

	resetBroker(
		t,
		ctx,
		d.RabbitMQ,
	)
	resetDynamoDB(
		t,
		ctx,
		d,
	)
	resetS3(
		t,
		ctx,
		d,
	)
	resetOpenSearch(
		t,
		ctx,
		d.OpenSearch,
	)
}

func resetBroker(
	t *testing.T,
	ctx context.Context,
	broker Service,
) {
	t.Helper()

	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodGet,
		broker.URL("/api/queues"),
		nil,
	)
	require.NoError(t, err)

	request.SetBasicAuth(broker.username, broker.password)

	response, err := resetHTTPClient.Do(request)
	require.NoError(t, err)
	defer response.Body.Close()

	require.Equal(
		t,
		http.StatusOK,
		response.StatusCode,
		"list RabbitMQ queues",
	)

	var queues []struct {
		Name  string `json:"name"`
		VHost string `json:"vhost"`
	}

	require.NoError(t, json.NewDecoder(response.Body).Decode(&queues))

	for _, queue := range queues {
		purge, err := http.NewRequestWithContext(
			ctx,
			http.MethodDelete,
			broker.URL("/api/queues/"+url.PathEscape(queue.VHost)+"/"+url.PathEscape(queue.Name)+"/contents"),
			nil,
		)
		require.NoError(t, err)

		purge.SetBasicAuth(broker.username, broker.password)

		purgeResponse, err := resetHTTPClient.Do(purge)
		require.NoError(t, err)

		purgeResponse.Body.Close()

		require.Contains(
			t,
			[]int{http.StatusNoContent, http.StatusNotFound},
			purgeResponse.StatusCode,
			"purge RabbitMQ queue %s",
			queue.Name,
		)
	}
}

func resetDynamoDB(
	t *testing.T,
	ctx context.Context,
	d Dependencies,
) {
	t.Helper()

	client := dynamodb.NewFromConfig(d.awsConfig(t), func(options *dynamodb.Options) {
		options.BaseEndpoint = aws.String(d.MiniStack.BaseURL())
	})

	var startTable *string

	for {
		tables, err := client.ListTables(ctx, &dynamodb.ListTablesInput{
			ExclusiveStartTableName: startTable,
		})
		require.NoError(t, err)

		for _, table := range tables.TableNames {
			wipeTable(
				t,
				ctx,
				client,
				table,
			)
		}

		if tables.LastEvaluatedTableName == nil {
			return
		}

		startTable = tables.LastEvaluatedTableName
	}
}

func wipeTable(
	t *testing.T,
	ctx context.Context,
	client *dynamodb.Client,
	table string,
) {
	t.Helper()

	description, err := client.DescribeTable(ctx, &dynamodb.DescribeTableInput{
		TableName: aws.String(table),
	})
	require.NoError(t, err)

	keyNames := make(
		[]string,
		0,
		len(description.Table.KeySchema),
	)

	for _, key := range description.Table.KeySchema {
		keyNames = append(keyNames, aws.ToString(key.AttributeName))
	}

	deleteItems(
		t,
		ctx,
		client,
		table,
		scanKeys(
			t,
			ctx,
			client,
			table,
			keyNames,
		),
	)
}

func scanKeys(
	t *testing.T,
	ctx context.Context,
	client *dynamodb.Client,
	table string,
	keyNames []string,
) []map[string]dynamodbtypes.AttributeValue {
	t.Helper()

	var (
		keys  []map[string]dynamodbtypes.AttributeValue
		start map[string]dynamodbtypes.AttributeValue
	)

	for {
		items, err := client.Scan(ctx, &dynamodb.ScanInput{
			TableName:         aws.String(table),
			ExclusiveStartKey: start,
		})
		require.NoError(t, err)

		for _, item := range items.Items {
			key := make(map[string]dynamodbtypes.AttributeValue, len(keyNames))

			for _, name := range keyNames {
				key[name] = item[name]
			}

			keys = append(keys, key)
		}

		if len(items.LastEvaluatedKey) == 0 {
			return keys
		}

		start = items.LastEvaluatedKey
	}
}

func deleteItems(
	t *testing.T,
	ctx context.Context,
	client *dynamodb.Client,
	table string,
	keys []map[string]dynamodbtypes.AttributeValue,
) {
	t.Helper()

	const batchSize = 25

	for len(keys) > 0 {
		size := min(len(keys), batchSize)

		requests := make(
			[]dynamodbtypes.WriteRequest,
			0,
			size,
		)

		for _, key := range keys[:size] {
			requests = append(requests, dynamodbtypes.WriteRequest{
				DeleteRequest: &dynamodbtypes.DeleteRequest{
					Key: key,
				},
			})
		}

		keys = keys[size:]

		for attempts := 0; len(requests) > 0; attempts++ {
			require.Less(
				t,
				attempts,
				10,
				"delete items from DynamoDB table %s",
				table,
			)

			output, err := client.BatchWriteItem(ctx, &dynamodb.BatchWriteItemInput{
				RequestItems: map[string][]dynamodbtypes.WriteRequest{
					table: requests,
				},
			})
			require.NoError(t, err)

			requests = output.UnprocessedItems[table]
		}
	}
}

func resetS3(
	t *testing.T,
	ctx context.Context,
	d Dependencies,
) {
	t.Helper()

	client := s3.NewFromConfig(d.awsConfig(t), func(options *s3.Options) {
		options.BaseEndpoint = aws.String(d.MiniStack.BaseURL())
		options.UsePathStyle = true
	})

	buckets, err := client.ListBuckets(ctx, &s3.ListBucketsInput{})
	require.NoError(t, err)

	for _, bucket := range buckets.Buckets {
		wipeBucket(
			t,
			ctx,
			client,
			aws.ToString(bucket.Name),
		)
	}
}

func wipeBucket(
	t *testing.T,
	ctx context.Context,
	client *s3.Client,
	bucket string,
) {
	t.Helper()

	var objects []s3types.ObjectIdentifier

	paginator := s3.NewListObjectsV2Paginator(client, &s3.ListObjectsV2Input{
		Bucket: aws.String(bucket),
	})

	for paginator.HasMorePages() {
		page, err := paginator.NextPage(ctx)
		require.NoError(t, err)

		for _, object := range page.Contents {
			objects = append(objects, s3types.ObjectIdentifier{Key: object.Key})
		}
	}

	deleteObjects(
		t,
		ctx,
		client,
		bucket,
		objects,
	)
}

func deleteObjects(
	t *testing.T,
	ctx context.Context,
	client *s3.Client,
	bucket string,
	objects []s3types.ObjectIdentifier,
) {
	t.Helper()

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
		require.NoError(t, err)
		require.Empty(
			t,
			output.Errors,
			"delete objects from S3 bucket %s",
			bucket,
		)

		objects = objects[size:]
	}
}

func resetOpenSearch(
	t *testing.T,
	ctx context.Context,
	search Service,
) {
	t.Helper()

	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodGet,
		search.URL("/_cat/indices?format=json&h=index"),
		nil,
	)
	require.NoError(t, err)

	response, err := resetHTTPClient.Do(request)
	require.NoError(t, err)
	defer response.Body.Close()

	require.Equal(
		t,
		http.StatusOK,
		response.StatusCode,
		"list OpenSearch indices",
	)

	var indices []struct {
		Index string `json:"index"`
	}

	require.NoError(t, json.NewDecoder(response.Body).Decode(&indices))

	for _, index := range indices {
		remove, err := http.NewRequestWithContext(
			ctx,
			http.MethodDelete,
			search.URL("/"+url.PathEscape(index.Index)),
			nil,
		)
		require.NoError(t, err)

		removeResponse, err := resetHTTPClient.Do(remove)
		require.NoError(t, err)

		removeResponse.Body.Close()

		require.Contains(
			t,
			[]int{http.StatusOK, http.StatusNotFound},
			removeResponse.StatusCode,
			"delete OpenSearch index %s",
			index.Index,
		)
	}
}

func (d Dependencies) awsConfig(t *testing.T) aws.Config {
	t.Helper()

	config, err := awsconfig.LoadDefaultConfig(
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
	require.NoError(t, err)

	return config
}
