package infra

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"time"
)

type queueInfo struct {
	Consumers int `json:"consumers"`
}

func waitForQueueConsumers(
	ctx context.Context,
	rabbitMQ Service,
	queue string,
	count int,
) error {
	ticker := time.NewTicker(readinessInterval)
	defer ticker.Stop()

	var lastErr error

	for {
		consumers, err := queueConsumers(ctx, rabbitMQ, queue)

		if err != nil {
			lastErr = err
		} else if consumers != count {
			lastErr = fmt.Errorf(
				"queue %s has %d consumers; want %d",
				queue,
				consumers,
				count,
			)
		} else {
			return nil
		}

		select {
		case <-ctx.Done():
			return fmt.Errorf(
				"wait for %s consumers: %w; last error: %v",
				queue,
				ctx.Err(),
				lastErr,
			)
		case <-ticker.C:
		}
	}
}

func queueConsumers(ctx context.Context, rabbitMQ Service, queue string) (int, error) {
	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodGet,
		rabbitMQ.URL("/api/queues/"+url.PathEscape(rabbitMQVhost)+"/"+queue),
		nil,
	)

	if err != nil {
		return 0, err
	}

	request.SetBasicAuth(rabbitMQ.username, rabbitMQ.password)

	response, err := httpClient.Do(request)

	if err != nil {
		return 0, err
	}

	defer response.Body.Close()

	if response.StatusCode != http.StatusOK {
		return 0, fmt.Errorf(
			"read queue %s: unexpected status %d",
			queue,
			response.StatusCode,
		)
	}

	data, err := io.ReadAll(response.Body)

	if err != nil {
		return 0, err
	}

	var info queueInfo

	if err := json.Unmarshal(data, &info); err != nil {
		return 0, fmt.Errorf("decode queue %s: %w", queue, err)
	}

	return info.Consumers, nil
}
