package rules

import "testing"

func TestFormat_KeyedLiteral_OneFieldPerLine(t *testing.T) {
	source := `package example

func Run() {
	config := Config{Host: "localhost", Port: 8080}
	_ = config
}
`

	expected := `package example

func Run() {
	config := Config{
		Host: "localhost",
		Port: 8080,
	}
	_ = config
}
`

	assertFormat(t, source, expected, MultilineCompositeLiterals)
}

func TestFormat_NestedKeyedLiterals_OneFieldPerLine(t *testing.T) {
	source := `package example

func Run() {
	result, err := a.client.Search(ctx, search.Query{
		Text: query.Text, CollectionID: query.CollectionID,
		ArchiveID: query.ArchiveID, SnapshotID: query.SnapshotID,
		CapturedFrom: query.CapturedFrom, CapturedTo: query.CapturedTo,
		Pagination: search.Pagination{Limit: query.Pagination.Limit, Cursor: query.Pagination.Cursor},
	})
	_, _ = result, err
}
`

	expected := `package example

func Run() {
	result, err := a.client.Search(ctx, search.Query{
		Text:         query.Text,
		CollectionID: query.CollectionID,
		ArchiveID:    query.ArchiveID,
		SnapshotID:   query.SnapshotID,
		CapturedFrom: query.CapturedFrom,
		CapturedTo:   query.CapturedTo,
		Pagination: search.Pagination{
			Limit:  query.Pagination.Limit,
			Cursor: query.Pagination.Cursor,
		},
	})
	_, _ = result, err
}
`

	assertFormat(t, source, expected, MultilineCompositeLiterals)
}

func TestFormat_UnkeyedLiteral_RemainsCompact(t *testing.T) {
	source := `package example

func Run() {
	numbers := []int{1, 2, 3}
	_ = numbers
}
`

	assertFormat(t, source, source, MultilineCompositeLiterals)
}

func TestFormat_EmptyLiteral_RemainsCompact(t *testing.T) {
	source := `package example

func Run() {
	config := Config{}
	_ = config
}
`

	assertFormat(t, source, source, MultilineCompositeLiterals)
}

func TestFormat_CommentsBetweenFields_ArePreserved(t *testing.T) {
	source := `package example

func Run() {
	config := Config{Host: "localhost", /* important */ Port: 8080}
	_ = config
}
`

	expected := `package example

func Run() {
	config := Config{Host: "localhost", /* important */ Port: 8080}
	_ = config
}
`

	assertFormat(t, source, expected, MultilineCompositeLiterals)
}

func TestFormat_AlreadyExpandedLiteral_RemainsUnchanged(t *testing.T) {
	source := `package example

func Run() {
	config := Config{
		Host: "localhost",
		Port: 8080,
	}
	_ = config
}
`

	assertFormat(t, source, source, MultilineCompositeLiterals)
}
