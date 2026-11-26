package testutil

import (
	"context"
	"testing"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/lemuel-manske/castellani/services/coordinator/topology"
	"github.com/stretchr/testify/require"
)

const tableWaitTimeout = 30 * time.Second

func setupDynamoDB(t *testing.T, client *dynamodb.Client) {
	t.Helper()

	for _, table := range coordinatorTables() {
		_, err := client.CreateTable(t.Context(), table)
		require.NoError(t, err)

		tableName := aws.ToString(table.TableName)
		t.Cleanup(func() {
			deleteDynamoDBTable(
				t,
				client,
				tableName,
			)
		})

		waitContext, cancel := context.WithTimeout(t.Context(), tableWaitTimeout)
		err = dynamodb.NewTableExistsWaiter(client).Wait(
			waitContext,
			&dynamodb.DescribeTableInput{
				TableName: aws.String(tableName),
			},
			tableWaitTimeout,
		)
		cancel()

		require.NoError(t, err)
	}
}

func deleteDynamoDBTable(
	t *testing.T,
	client *dynamodb.Client,
	tableName string,
) {
	t.Helper()

	ctx, cancel := context.WithTimeout(context.Background(), tableWaitTimeout)
	defer cancel()

	_, err := client.DeleteTable(ctx, &dynamodb.DeleteTableInput{
		TableName: aws.String(tableName),
	})

	if err != nil {
		t.Errorf(
			"delete DynamoDB table %s: %v",
			tableName,
			err,
		)

		return
	}

	err = dynamodb.NewTableNotExistsWaiter(client).Wait(
		ctx,
		&dynamodb.DescribeTableInput{
			TableName: aws.String(tableName),
		},
		tableWaitTimeout,
	)

	if err != nil {
		t.Errorf(
			"wait for DynamoDB table %s to be deleted: %v",
			tableName,
			err,
		)
	}
}

func coordinatorTables() []*dynamodb.CreateTableInput {
	return []*dynamodb.CreateTableInput{
		{
			TableName:   aws.String(topology.ArchivesTable),
			BillingMode: types.BillingModePayPerRequest,
			AttributeDefinitions: []types.AttributeDefinition{
				attribute("archiveId"),
				attribute("recoveryKey"),
				attribute("updatedAt"),
			},
			KeySchema: []types.KeySchemaElement{
				key("archiveId", types.KeyTypeHash),
			},
			GlobalSecondaryIndexes: []types.GlobalSecondaryIndex{
				{
					IndexName: aws.String("recoveryKey-updatedAt-index"),
					KeySchema: []types.KeySchemaElement{
						key("recoveryKey", types.KeyTypeHash),
						key("updatedAt", types.KeyTypeRange),
					},
					Projection: &types.Projection{
						ProjectionType: types.ProjectionTypeAll,
					},
				},
			},
		},
		{
			TableName:   aws.String(topology.SubmissionsTable),
			BillingMode: types.BillingModePayPerRequest,
			AttributeDefinitions: []types.AttributeDefinition{
				attribute("idempotencyKey"),
			},
			KeySchema: []types.KeySchemaElement{
				key("idempotencyKey", types.KeyTypeHash),
			},
		},
		{
			TableName:   aws.String(topology.OutboxTable),
			BillingMode: types.BillingModePayPerRequest,
			AttributeDefinitions: []types.AttributeDefinition{
				attribute("messageId"),
			},
			KeySchema: []types.KeySchemaElement{
				key("messageId", types.KeyTypeHash),
			},
		},
		{
			TableName:   aws.String(topology.InboxTable),
			BillingMode: types.BillingModePayPerRequest,
			AttributeDefinitions: []types.AttributeDefinition{
				attribute("messageId"),
			},
			KeySchema: []types.KeySchemaElement{
				key("messageId", types.KeyTypeHash),
			},
		},
	}
}

func attribute(name string) types.AttributeDefinition {
	return types.AttributeDefinition{
		AttributeName: aws.String(name),
		AttributeType: types.ScalarAttributeTypeS,
	}
}

func key(name string, keyType types.KeyType) types.KeySchemaElement {
	return types.KeySchemaElement{
		AttributeName: aws.String(name),
		KeyType:       keyType,
	}
}
