package rules

import "testing"

func TestFormat_CompactStruct_ExpandsFields(t *testing.T) {
	source := `package example

type ValidationError struct{ Cause error }
`

	expected := `package example

type ValidationError struct {
	Cause error
}
`

	assertFormat(t, source, expected, MultilineStructs)
}

func TestFormat_CompactStruct_WithMultipleFields(t *testing.T) {
	source := `package example

type Item struct{ Name string; ID int }
`

	expected := `package example

type Item struct {
	Name string
	ID   int
}
`

	assertFormat(t, source, expected, MultilineStructs)
}

func TestFormat_EmptyStruct_RemainsCompact(t *testing.T) {
	source := `package example

type Marker struct{}
`

	assertFormat(t, source, source, MultilineStructs)
}

func TestFormat_NestedStruct_ExpandsFieldIndentation(t *testing.T) {
	source := `package example

type Result struct {
	Inner struct{ Cause error }
}
`

	expected := `package example

type Result struct {
	Inner struct {
		Cause error
	}
}
`

	assertFormat(t, source, expected, MultilineStructs)
}

func TestFormat_CompactStruct_WithFieldTag(t *testing.T) {
	source := `package example

type Item struct{ Name string \`json:"name"\` }
`

	expected := `package example

type Item struct {
	Name string \`json:"name"\`
}
`

	assertFormat(t, source, expected, MultilineStructs)
}

func TestFormat_CombinedSpacingAndStructLayout(t *testing.T) {
	source := `package example

type ValidationError struct{ Cause error }

func Get() (*ValidationError, error) {
	if true {
		return nil, nil
	}
	return nil, nil
}
`

	expected := `package example

type ValidationError struct {
	Cause error
}

func Get() (*ValidationError, error) {
	if true {
		return nil, nil
	}

	return nil, nil
}
`

	assertFormat(t, source, expected, ReturnSpacing, MultilineStructs)
}
