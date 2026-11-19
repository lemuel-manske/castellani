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
