package persistence

import (
 "context"
 "encoding/json"
 "errors"
 "fmt"
 "time"

 "github.com/aws/aws-sdk-go-v2/aws"
 "github.com/aws/aws-sdk-go-v2/service/dynamodb"
 "github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
 "github.com/lemuel-manske/unnamed/services/coordinator/application"
 "github.com/lemuel-manske/unnamed/services/coordinator/internal/archive"
)

const retention = 24 * time.Hour

type Client interface {
 TransactWriteItems(context.Context, *dynamodb.TransactWriteItemsInput, ...func(*dynamodb.Options)) (*dynamodb.TransactWriteItemsOutput,error)
 GetItem(context.Context, *dynamodb.GetItemInput, ...func(*dynamodb.Options)) (*dynamodb.GetItemOutput,error)
}

type Store struct {
 db Client
 runs string
 keys string
 outbox string
}

func New(db Client, prefix string) Store {
 return Store{db:db, runs:prefix+"coordinator_archive_runs",keys:prefix+"coordinator_submission_keys",outbox:prefix+"coordinator_outbox"}
}

func (s Store) Admit(ctx context.Context, key, digest string, accepted archive.AcceptedResponse, submission archive.Submission, now time.Time) (archive.AcceptedResponse,error) {
 response, err := json.Marshal(accepted)
 if err != nil { return archive.AcceptedResponse{},err }
 start := map[string]any{"archiveId":accepted.ArchiveID, "seedUrl":submission.SeedURL,"maxDepth":*submission.MaxDepth,"maxPages":*submission.MaxPages}
 if submission.CollectionID != "" { start["collectionId"] = submission.CollectionID }
 if len(submission.AllowedOrigins)>0 { start["allowedOrigins"] = submission.AllowedOrigins }
 if submission.AuthGeneration != nil { start["authGeneration"] = *submission.AuthGeneration }
 envelope, err := json.Marshal(map[string]any{
  "messageId":accepted.ArchiveID+":start:1",
  "correlationId":accepted.ArchiveID,
  "type":"StartCrawl","version":1,"occurredAt":now.Format(time.RFC3339Nano),"payload":start,
 })
 if err != nil { return archive.AcceptedResponse{},err }
 pending := archive.Status{ArchiveID:accepted.ArchiveID,Status:archive.Accepted,Replay:archive.Replay{Status:"NOT_READY"},Search:archive.Search{Status:"PENDING"}}
 status, err := json.Marshal(pending)
 if err != nil { return archive.AcceptedResponse{},err }
 expires := now.Add(retention).Unix()
 _,err = s.db.TransactWriteItems(ctx,&dynamodb.TransactWriteItemsInput{
  TransactItems: []types.TransactWriteItem{
   {Put:&types.Put{TableName:aws.String(s.keys),Item:map[string]types.AttributeValue{
    "idempotencyKey":str(key),"digest":str(digest),"archiveId":str(accepted.ArchiveID),
    "response":str(string(response)),"expiresAt":num(expires),
   },ConditionExpression:aws.String("attribute_not_exists(idempotencyKey)")}},
   {Put:&types.Put{TableName:aws.String(s.runs),Item:map[string]types.AttributeValue{
    "archiveId":str(accepted.ArchiveID),"status":str(string(status)),"decision":str("NONE"),"revision":num(0),
   },ConditionExpression:aws.String("attribute_not_exists(archiveId)")}},
   {Put:&types.Put{TableName:aws.String(s.outbox),Item:map[string]types.AttributeValue{
    "messageId":str(accepted.ArchiveID+":start:1"),"envelope":str(string(envelope)),
    "state":str("PENDING"),"destination":str("capture.start-crawl"),
   },ConditionExpression:aws.String("attribute_not_exists(messageId)")}},
  },
 })
 if err == nil { return accepted,nil }
 var canceled *types.TransactionCanceledException
 if !errors.As(err,&canceled) { return archive.AcceptedResponse{},fmt.Errorf("admit archive: %w",err) }
 // A failed conditional admission may be a duplicate key or an unrelated transactional failure.
 existing, readErr := s.db.GetItem(ctx,&dynamodb.GetItemInput{
  TableName:aws.String(s.keys),Key:map[string]types.AttributeValue{"idempotencyKey":str(key)},ConsistentRead:aws.Bool(true),
 })
 if readErr != nil { return archive.AcceptedResponse{},fmt.Errorf("resolve admission: %w",readErr) }
 if len(existing.Item)==0 { return archive.AcceptedResponse{},fmt.Errorf("admit archive: %w",err) }
 if stringAttr(existing.Item,"digest") != digest { return archive.AcceptedResponse{},application.ErrConflict }
 var stored archive.AcceptedResponse
 if err := json.Unmarshal([]byte(stringAttr(existing.Item,"response")),&stored);err != nil { return archive.AcceptedResponse{},fmt.Errorf("decode admitted response: %w",err) }
 return stored,nil
}

func (s Store) Status(ctx context.Context,id string) (archive.Status,error) {
 record,err := s.db.GetItem(ctx,&dynamodb.GetItemInput{
  TableName:aws.String(s.runs),Key:map[string]types.AttributeValue{"archiveId":str(id)},ConsistentRead:aws.Bool(true),
 })
 if err != nil { return archive.Status{},fmt.Errorf("read archive: %w",err) }
 if len(record.Item)==0 { return archive.Status{},application.ErrNotFound }
 var status archive.Status
 if err := json.Unmarshal([]byte(stringAttr(record.Item,"status")),&status);err != nil { return archive.Status{},fmt.Errorf("decode archive status: %w",err) }
 return status,nil
}

func str(s string) types.AttributeValue { return &types.AttributeValueMemberS{Value:s} }
func num(n int64) types.AttributeValue { return &types.AttributeValueMemberN{Value:fmt.Sprint(n)} }
func stringAttr(item map[string]types.AttributeValue,key string) string {
 value,ok := item[key].(*types.AttributeValueMemberS)
 if !ok { return "" }
 return value.Value
}
