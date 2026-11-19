package rules

import "testing"

func TestFormat_IfAfterStatement_HasBlankLine(t *testing.T) {
	source := `package example

func Run() {
	x := 1
	if x > 0 {
		println(x)
	}
}
`

	expected := `package example

func Run() {
	x := 1

	if x > 0 {
		println(x)
	}
}
`

	assertFormat(t, source, expected, IfSpacing)
}

func TestFormat_FirstIfInBlock_NoExtraBlankLine(t *testing.T) {
	source := `package example

func Run() {
	if true {
		println("ok")
	}
}
`

	assertFormat(t, source, source, IfSpacing)
}

func TestFormat_IfWithLeadingComment_PreservesComment(t *testing.T) {
	source := `package example

func Run() {
	x := 1
	// x is checked below.
	if x > 0 {
		println(x)
	}
}
`

	assertFormat(t, source, source, IfSpacing)
}

func TestFormat_CombinedRules_RemainsStable(t *testing.T) {
	source := `package example

type Service struct{}

const DefaultName = "service"

func Run(a string, b int, c bool) {
	println(a, b, c)
	if c {
		println(DefaultName)
	}
}
`

	expected := `package example

const DefaultName = "service"

type Service struct{}

func Run(
	a string,
	b int,
	c bool,
) {
	println(
		a,
		b,
		c,
	)

	if c {
		println(DefaultName)
	}
}
`

	assertFormat(t, source, expected, DeclarationsOrder, MultilineSignatures, MultilineCalls, IfSpacing)
}

func TestFormat_ReturnAfterIf_HasBlankLine(t *testing.T) {
	source := `package example

func Get() error {
	if true {
		return nil
	}
	return nil
}
`

	expected := `package example

func Get() error {
	if true {
		return nil
	}

	return nil
}
`

	assertFormat(t, source, expected, ReturnSpacing)
}

func TestFormat_ReturnAfterIf_PreservesExistingSpacing(t *testing.T) {
	source := `package example

func Get() error {
	if true {
		return nil
	}

	return nil
}
`

	assertFormat(t, source, source, ReturnSpacing)
}

func TestFormat_ReturnAfterIf_WithComment_LeavesCommentAttached(t *testing.T) {
	source := `package example

func Get() error {
	if true {
		return nil
	}
	// This is a fallback.
	return nil
}
`

	assertFormat(t, source, source, ReturnSpacing)
}

func TestFormat_ReturnAtStartOfBlock_DoesNotAddBlankLine(t *testing.T) {
	source := `package example

func Get() error {
	return nil
}
`

	assertFormat(t, source, source, ReturnSpacing)
}
