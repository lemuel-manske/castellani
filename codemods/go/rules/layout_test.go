package rules

import "testing"

func TestFormat_LongSignature_OneParameterPerLine(t *testing.T) {
	source := `package example

func Run(ctx string, id int, enabled bool) error {
	return nil
}
`

	expected := `package example

func Run(
	ctx string,
	id int,
	enabled bool,
) error {
	return nil
}
`

	assertFormat(t, source, expected, MultilineSignatures)
}

func TestFormat_ShortSignature_RemainsCompact(t *testing.T) {
	source := `package example

func Run(id int) int {
	return id
}
`

	assertFormat(t, source, source, MultilineSignatures)
}

func TestFormat_LongCall_OneArgumentPerLine(t *testing.T) {
	source := `package example

func Run() {
	println("one", "two", "three")
}
`

	expected := `package example

func Run() {
	println(
		"one",
		"two",
		"three",
	)
}
`

	assertFormat(t, source, expected, MultilineCalls)
}

func TestFormat_NestedCalls_BothExpanded(t *testing.T) {
	source := `package example

func Run() {
	println(append([]int{}, 1, 2, 3), "two", "three")
}
`

	expected := `package example

func Run() {
	println(
		append(
			[]int{},
			1,
			2,
			3,
		),
		"two",
		"three",
	)
}
`

	assertFormat(t, source, expected, MultilineCalls)
}

func TestFormat_CommentsInsideCall_AreNotMoved(t *testing.T) {
	source := `package example

func Run() {
	println("one" /* important */, "two", "three")
}
`

	assertFormat(t, source, source, MultilineCalls)
}

func TestFormat_ShortCall_RemainsCompact(t *testing.T) {
	source := `package example

func Run() {
	println("one", "two")
}
`

	assertFormat(t, source, source, MultilineCalls)
}
