package infra

import (
	"fmt"

	"github.com/testcontainers/testcontainers-go/modules/compose"
)

func newComposeStack(composeFiles ...string) (stack *compose.DockerCompose, err error) {
	defer func() {
		if recovered := recover(); recovered != nil {
			err = fmt.Errorf("create compose stack: %v", recovered)
		}
	}()

	return compose.NewDockerComposeWith(compose.WithStackFiles(composeFiles...))
}
