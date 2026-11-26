package tests

import (
	"os"
	"testing"

	"github.com/lemuel-manske/castellani/tests/internal/infra"
)

func TestMain(m *testing.M) {
	code := m.Run()

	infra.Stop()

	os.Exit(code)
}
