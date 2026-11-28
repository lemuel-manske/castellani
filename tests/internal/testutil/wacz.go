package testutil

import (
	"archive/zip"
	"bytes"
	"compress/gzip"
	"encoding/json"
	"io"
	"strings"
	"testing"

	"github.com/lemuel-manske/castellani/tests/internal/contracts"
	"github.com/stretchr/testify/require"
)

func WaczDescriptor(
	t *testing.T,
	body string,
) map[string]any {
	t.Helper()

	reader, err := zip.NewReader(
		strings.NewReader(body),
		int64(len(body)),
	)
	require.NoError(t, err)

	descriptor, err := reader.Open("datapackage.json")
	require.NoError(t, err)

	var document map[string]any

	require.NoError(t, json.NewDecoder(descriptor).Decode(&document))
	require.NoError(t, descriptor.Close())

	return document
}

func WaczRecords(
	t *testing.T,
	body string,
) string {
	t.Helper()

	reader, err := zip.NewReader(
		strings.NewReader(body),
		int64(len(body)),
	)
	require.NoError(t, err)

	var records strings.Builder

	for _, file := range reader.File {
		if !strings.HasPrefix(file.Name, "archive/") {
			continue
		}

		entry, err := file.Open()
		require.NoError(t, err)

		compressed, err := io.ReadAll(entry)
		require.NoError(t, err)
		require.NoError(t, entry.Close())

		warFile, err := gzip.NewReader(bytes.NewReader(compressed))
		require.NoError(t, err)

		content, err := io.ReadAll(warFile)
		require.NoError(t, err)
		require.NoError(t, warFile.Close())

		records.Write(content)
	}

	return records.String()
}

func RequireWarcRecordsForPages(
	t *testing.T,
	records string,
	pages []contracts.PageOutcome,
) {
	t.Helper()

	require.NotEmpty(t, records)

	for _, page := range pages {
		require.Contains(
			t,
			records,
			"WARC-Target-URI: "+page.URL,
			"missing WARC record for %s",
			page.URL,
		)
	}
}
