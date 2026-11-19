package api

import (
 "bytes"
 "encoding/json"
 "errors"
 "io"
 "log/slog"
 "mime"
 "net/http"
 "strings"

 "github.com/go-chi/chi/v5"
 "github.com/lemuel-manske/unnamed/services/coordinator/application"
 "github.com/lemuel-manske/unnamed/services/coordinator/internal/archive"
)

const (
 maxRequestBytes = 64 << 10
 healthLive = "/health/live"
 healthReady = "/health/ready"
)

type Archives interface {
 Create(*http.Request, string, archive.Submission) (archive.AcceptedResponse,error)
 Get(*http.Request,string) (archive.Status,error)
}

type serviceAdapter struct { app application.Service }
func (s serviceAdapter) Create(r *http.Request,key string,submission archive.Submission)(archive.AcceptedResponse,error) {
 return s.app.Create(r.Context(),key,submission)
}
func (s serviceAdapter) Get(r *http.Request,id string)(archive.Status,error) {
 return s.app.Get(r.Context(),id)
}

func NewRouter(app application.Service,ready func()bool,logger *slog.Logger) http.Handler {
 return Router(serviceAdapter{app:app},ready,logger)
}

func Router(service Archives,ready func()bool,logger *slog.Logger) http.Handler {
 r:=chi.NewRouter()
 r.Use(func(next http.Handler) http.Handler {
  return http.HandlerFunc(func(w http.ResponseWriter,req *http.Request) {
   defer func() {
    if recover()!=nil {
     logger.Error("coordinator handler panic","path",req.URL.Path)
     problem(w,req,http.StatusInternalServerError,"internal","Internal Server Error","Request handling failed.")
    }
   }()
   next.ServeHTTP(w,req)
  })
 })
 r.Get(healthLive,func(w http.ResponseWriter,_ *http.Request){w.Header().Set("Content-Type","text/plain; charset=utf-8");_,_=io.WriteString(w,"ok\n")})
 r.Get(healthReady,func(w http.ResponseWriter,_ *http.Request){
  if !ready() { http.Error(w,"unavailable",http.StatusServiceUnavailable);return }
  w.Header().Set("Content-Type","text/plain; charset=utf-8");_,_=io.WriteString(w,"ok\n")
 })
 r.Post("/archives",func(w http.ResponseWriter,req *http.Request){create(w,req,service)})
 r.Get("/archives/{archiveId}",func(w http.ResponseWriter,req *http.Request){status(w,req,service,chi.URLParam(req,"archiveId"))})
 return r
}

func create(w http.ResponseWriter,r *http.Request,service Archives) {
 key:=r.Header.Get("Idempotency-Key")
 if len(key)<8 || len(key)>200 || strings.TrimSpace(key)!=key {
  problem(w,r,http.StatusBadRequest,"idempotency-key","Invalid Idempotency Key","Idempotency-Key must be 8 to 200 characters without surrounding whitespace.")
  return
 }
 mediaType,_,err:=mime.ParseMediaType(r.Header.Get("Content-Type"))
 if err!=nil || mediaType!="application/json" {
  problem(w,r,http.StatusBadRequest,"content-type","Invalid Content Type","Expected application/json.")
  return
 }
 raw,err:=io.ReadAll(http.MaxBytesReader(w,r.Body,maxRequestBytes))
 if err!=nil {problem(w,r,http.StatusBadRequest,"invalid-json","Invalid Request","Invalid or oversized request.");return}
 decoder:=json.NewDecoder(bytes.NewReader(raw))
 decoder.DisallowUnknownFields()
 var submission archive.Submission
 if err:=decoder.Decode(&submission);err!=nil {problem(w,r,http.StatusBadRequest,"invalid-json","Invalid Request","Expected a valid archive JSON object.");return}
 var extra any
 if err:=decoder.Decode(&extra);!errors.Is(err,io.EOF) {problem(w,r,http.StatusBadRequest,"invalid-json","Invalid Request","Expected exactly one JSON object.");return}
 accepted,err:=service.Create(r,key,submission)
 if err!=nil {writeError(w,r,err);return}
 w.Header().Set("Location",accepted.StatusURL)
 respond(w,http.StatusAccepted,accepted)
}

func status(w http.ResponseWriter,r *http.Request,service Archives,id string) {
 record,err:=service.Get(r,id)
 if err!=nil {writeError(w,r,err);return}
 respond(w,http.StatusOK,record)
}

func writeError(w http.ResponseWriter,r *http.Request,err error) {
 switch {
 case errors.Is(err,application.ErrInvalid):
  problem(w,r,http.StatusUnprocessableEntity,"invalid-archive","Invalid Archive",err.Error())
 case errors.Is(err,application.ErrConflict):
  problem(w,r,http.StatusConflict,"idempotency-conflict","Conflict","Idempotency-Key was used for a different archive request.")
 case errors.Is(err,application.ErrNotFound):
  problem(w,r,http.StatusNotFound,"not-found","Not Found","Archive does not exist.")
 default:
  problem(w,r,http.StatusServiceUnavailable,"coordinator-unavailable","Coordinator Unavailable","The operation could not be confirmed. Retry with the same Idempotency-Key.")
 }
}

func problem(w http.ResponseWriter,r *http.Request,code int,kind,title,detail string) {
 w.Header().Set("Content-Type","application/problem+json")
 w.Header().Set("Cache-Control","no-store")
 w.WriteHeader(code)
 _=json.NewEncoder(w).Encode(map[string]any{"type":"urn:distributed-web-archive:problem:"+kind,"title":title,"status":code,"detail":detail,"instance":r.URL.Path})
}
func respond(w http.ResponseWriter,code int,payload any) {
 w.Header().Set("Content-Type","application/json")
 w.Header().Set("Cache-Control","no-store")
 w.WriteHeader(code)
 _=json.NewEncoder(w).Encode(payload)
}
