package main

import (
	"context"
	"log/slog"
	"time"

	"github.com/lemuel-manske/castellani/services/coordinator/application"
	"github.com/lemuel-manske/castellani/services/coordinator/messaging/dispatcher"
	"github.com/lemuel-manske/castellani/services/coordinator/messaging/rabbitmq"
)

const (
	dispatchInterval = 500 * time.Millisecond
	workerRetryDelay = 2 * time.Second
)

func StartWorkers(
	ctx context.Context,
	logger *slog.Logger,
	dispatcher *dispatcher.Dispatcher,
	consumer *rabbitmq.RabbitConsumer,
	app *application.Application,
	reconcileInterval time.Duration,
	stalledWorkflowAge time.Duration,
) {
	go func() {
		for ctx.Err() == nil {
			found, err := dispatcher.Dispatch(ctx)

			if err != nil && ctx.Err() == nil {
				logger.Error(
					"outbox dispatch failed",
					"error",
					err,
				)
			}

			delay := dispatchInterval

			if err != nil {
				delay = workerRetryDelay
			} else if found {
				continue
			}

			if !sleep(ctx, delay) {
				return
			}
		}
	}()

	go func() {
		for ctx.Err() == nil {
			err := consumer.Consume(ctx, app.HandleEvent)

			if err != nil && ctx.Err() == nil {
				logger.Error(
					"event consumer stopped",
					"error",
					err,
				)
			}

			if !sleep(ctx, workerRetryDelay) {
				return
			}
		}
	}()

	go func() {
		for ctx.Err() == nil {
			reconciled, err := app.ReconcileStalled(ctx, stalledWorkflowAge)

			if err != nil && ctx.Err() == nil {
				logger.Error(
					"archive reconciliation failed",
					"error",
					err,
				)
			} else if reconciled > 0 {
				logger.Info(
					"stalled archive workflows rescheduled",
					"count",
					reconciled,
				)
			}

			if !sleep(ctx, reconcileInterval) {
				return
			}
		}
	}()
}

func sleep(ctx context.Context, duration time.Duration) bool {
	timer := time.NewTimer(duration)
	defer timer.Stop()

	select {
	case <-ctx.Done():
		return false
	case <-timer.C:
		return true
	}
}
