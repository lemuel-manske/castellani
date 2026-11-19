package codemods

import (
	"bytes"
	"testing"
)

func assertFormat(t *testing.T, source, expected string, rules ...Rule) {
	t.Helper()

	actual, err := Format([]byte(source), rules...)
	if err != nil {
		t.Fatal(err)
	}

	if string(actual) != expected {
		t.Errorf("unexpected format\nexpected:\n%s\nactual:\n%s", expected, actual)
	}

	again, err := Format(actual, rules...)
	if err != nil {
		t.Fatal(err)
	}

	if !bytes.Equal(again, actual) {
		t.Errorf("format is not idempotent\nfirst:\n%s\nsecond:\n%s", actual, again)
	}
}

func assertFormatError(t *testing.T, source string, rules ...Rule) {
	t.Helper()

	_, err := Format([]byte(source), rules...)
	if err == nil {
		t.Fatal("expected a formatting error")
	}
}

func TestFormat_NoRules_UsesGoFmt(t *testing.T) {
	source := `package example

type Service struct {Name string}
`

	expected := `package example

type Service struct{ Name string }
`

	assertFormat(t, source, expected)
}

func TestFormat_InvalidSource_ReturnsError(t *testing.T) {
	assertFormatError(t, "package example\nfunc broken( {\n")
}

func TestFormat_NilRule_ReturnsError(t *testing.T) {
	assertFormatError(t, "package example\n", nil)
}

func TestFormat_MultipleRules(t *testing.T) {
	source := `package example

type Service struct{}

const DefaultName = "service"
`

	expected := `package example

const DefaultName = "service"

type Service struct{}
`

	assertFormat(t, source, expected, DeclarationsOrder, DeclarationsOrder)
}
