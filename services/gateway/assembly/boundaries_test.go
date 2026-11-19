package assembly_test

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

func TestOutboundClients_DoNotImportApplication(t *testing.T) {
	files, err := filepath.Glob("../clients/*/*.go")
	require.NoError(t, err)
	require.NotEmpty(t, files)

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
			importPath, err := strconv.Unquote(declaration.Path.Value)
			require.NoError(t, err)

			assert.NotContains(
				t,
				importPath,
				"/application",
				path,
			)
			assert.NotContains(
				t,
				importPath,
				"/assembly",
				path,
			)
		}
	}
}
