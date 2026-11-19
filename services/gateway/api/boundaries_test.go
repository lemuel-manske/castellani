package api_test

import (
	"go/parser"
	"go/token"
	"path/filepath"
	"strconv"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestGatewayAPI_DoesNotImportOutboundClients(t *testing.T) {
	directories := []string{".", "archive", "session", "search", "params", "response"}

	for _, directory := range directories {
		files, err := filepath.Glob(filepath.Join(directory, "*.go"))
		require.NoError(t, err)

		for _, path := range files {
			if strings.HasSuffix(path, "_test.go") {
				continue
			}

			source, err := parser.ParseFile(
				token.NewFileSet(),
				path,
				nil,
				parser.ImportsOnly,
			)
			require.NoError(t, err)

			for _, declaration := range source.Imports {
				dependency, err := strconv.Unquote(declaration.Path.Value)
				require.NoError(t, err)

				assert.NotContains(
					t,
					dependency,
					"/clients/",
					path,
				)
				assert.NotContains(
					t,
					dependency,
					"/internal/",
					path,
				)
				assert.NotContains(
					t,
					dependency,
					"/assembly",
					path,
				)
			}
		}
	}
}
