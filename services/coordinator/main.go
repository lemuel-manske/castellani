package main

import (
 "context"
 "errors"
 "fmt"
 "log/slog"
 "net"
 "net/http"
 "os"
 "os/signal"
 "syscall"
 "time"

 "github.com/aws/aws-sdk-go-v2/config"
 "github.com/aws/aws-sdk-go-v2/service/dynamodb"
 "github.com/lemuel-manske/unnamed/services/coordinator/api"
 "github.com/lemuel-manske/unnamed/services/coordinator/application"
 "github.com/lemuel-manske/unnamed/services/coordinator/internal/persistence"
)

const (
 defaultAddress = ":8081"
 shutdownTimeout = 10 * time.Second
 headerTimeout = 5 * time.Second
)

func main() {
 logger:=slog.New(slog.NewJSONHandler(os.Stdout,nil)).With("service","coordinator")
 if err:=run(logger);err!=nil {logger.Error("coordinator stopped","error",err);os.Exit(1)}
}

func run(logger *slog.Logger) error {
 address:=os.Getenv("COORDINATOR_ADDR")
 if address=="" {address=defaultAddress}
 if _,_,err:=net.SplitHostPort(address);err!=nil {return fmt.Errorf("invalid COORDINATOR_ADDR: %w",err)}
 ctx,stop:=signal.NotifyContext(context.Background(),os.Interrupt,syscall.SIGTERM)
 defer stop()
 awsConfig,err:=config.LoadDefaultConfig(ctx)
 if err!=nil {return fmt.Errorf("load DynamoDB config: %w",err)}
 db:=dynamodb.NewFromConfig(awsConfig)
 store:=persistence.New(db,os.Getenv("COORDINATOR_TABLE_PREFIX"))
 listener,err:=net.Listen("tcp",address)
 if err!=nil {return fmt.Errorf("listen: %w",err)}
 defer listener.Close()
 server:=&http.Server{Handler:api.NewRouter(application.New(store),func()bool{return ctx.Err()==nil},logger),ReadHeaderTimeout:headerTimeout}
 stopped:=make(chan error,1)
 go func(){stopped<-server.Serve(listener)}()
 logger.Info("coordinator listening","address",listener.Addr().String())
 select {
 case err:=<-stopped:
  return fmt.Errorf("HTTP listener stopped: %w",err)
 case <-ctx.Done():
 }
 shutdownCtx,cancel:=context.WithTimeout(context.Background(),shutdownTimeout)
 defer cancel()
 shutdownErr:=server.Shutdown(shutdownCtx)
 if shutdownErr!=nil {shutdownErr=errors.Join(shutdownErr,server.Close())}
 serveErr:=<-stopped
 if !errors.Is(serveErr,http.ErrServerClosed) {return errors.Join(shutdownErr,serveErr)}
 return shutdownErr
}
