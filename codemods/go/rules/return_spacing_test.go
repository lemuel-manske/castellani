package rules

import "testing"

func TestFormat_ReturnAfterProblemResponse_HasBlankLine(t *testing.T) {
	source := `package example

func Handle(w, r any, err error) {
	if err != nil {
		httpx.WriteProblem(w, httpx.NewProblem(
			r,
			400,
			"invalid-pagination",
			"Invalid Pagination",
			err.Error(),
		))
		return
	}
}
`

	expected := `package example

func Handle(w, r any, err error) {
	if err != nil {
		httpx.WriteProblem(w, httpx.NewProblem(
			r,
			400,
			"invalid-pagination",
			"Invalid Pagination",
			err.Error(),
		))

		return
	}
}
`

	assertFormat(t, source, expected, ReturnSpacing)
}

func TestFormat_ReturnAfterAssignment_HasBlankLine(t *testing.T) {
	source := `package example

func Run() int {
	result := 42
	return result
}
`

	expected := `package example

func Run() int {
	result := 42

	return result
}
`

	assertFormat(t, source, expected, ReturnSpacing)
}

func TestFormat_ReturnAfterDefer_HasBlankLine(t *testing.T) {
	source := `package example

func Run() {
	defer cleanup()
	return
}
`

	expected := `package example

func Run() {
	defer cleanup()

	return
}
`

	assertFormat(t, source, expected, ReturnSpacing)
}

func TestFormat_ReturnAfterGoroutine_HasBlankLine(t *testing.T) {
	source := `package example

func Run() {
	go work()
	return
}
`

	expected := `package example

func Run() {
	go work()

	return
}
`

	assertFormat(t, source, expected, ReturnSpacing)
}

func TestFormat_ReturnAfterChannelSend_HasBlankLine(t *testing.T) {
	source := `package example

func Run(ch chan int) {
	ch <- 1
	return
}
`

	expected := `package example

func Run(ch chan int) {
	ch <- 1

	return
}
`

	assertFormat(t, source, expected, ReturnSpacing)
}

func TestFormat_ReturnAfterLoop_HasBlankLine(t *testing.T) {
	source := `package example

func Run() {
	for n := 0; n < 2; n++ {
		work()
	}
	return
}
`

	expected := `package example

func Run() {
	for n := 0; n < 2; n++ {
		work()
	}

	return
}
`

	assertFormat(t, source, expected, ReturnSpacing)
}

func TestFormat_ReturnInsideSwitchCase_HasBlankLine(t *testing.T) {
	source := `package example

func Run(n int) int {
	switch n {
	case 1:
		result := n
		return result
	default:
		return 0
	}
}
`

	expected := `package example

func Run(n int) int {
	switch n {
	case 1:
		result := n

		return result
	default:
		return 0
	}
}
`

	assertFormat(t, source, expected, ReturnSpacing)
}

func TestFormat_ReturnInsideSelectCase_HasBlankLine(t *testing.T) {
	source := `package example

func Run(ch <-chan int) int {
	select {
	case n := <-ch:
		print(n)
		return n
	default:
		return 0
	}
}
`

	expected := `package example

func Run(ch <-chan int) int {
	select {
	case n := <-ch:
		print(n)

		return n
	default:
		return 0
	}
}
`

	assertFormat(t, source, expected, ReturnSpacing)
}

func TestFormat_ReturnAtBeginningOfBlock_RemainsAdjacent(t *testing.T) {
	source := `package example

func Run() {
	return
}
`

	assertFormat(t, source, source, ReturnSpacing)
}

func TestFormat_ReturnFollowingLeadingComment_DoesNotDetachComment(t *testing.T) {
	source := `package example

func Run() {
	work()
	// Explain the return.
	return
}
`

	assertFormat(t, source, source, ReturnSpacing)
}

func TestFormat_ReturnFollowingTrailingComment_DoesNotMoveComment(t *testing.T) {
	source := `package example

func Run() {
	work() // important
	return
}
`

	assertFormat(t, source, source, ReturnSpacing)
}

func TestFormat_ReturnAlreadySeparated_RemainsUnchanged(t *testing.T) {
	source := `package example

func Run() {
	work()

	return
}
`

	assertFormat(t, source, source, ReturnSpacing)
}

func TestFormat_SemicolonSeparatedReturn_BecomesSeparateParagraph(t *testing.T) {
	source := `package example

func Run() int {
	result := 1; return result
}
`

	expected := `package example

func Run() int {
	result := 1

	return result
}
`

	assertFormat(t, source, expected, ReturnSpacing)
}

func TestFormat_LabeledReturn_RemainsAttachedToLabel(t *testing.T) {
	source := `package example

func Run() {
	work()
done:
	return
}
`

	assertFormat(t, source, source, ReturnSpacing)
}

func TestFormat_IfAndReturnSpacing_ComposeWithoutDuplicateBlankLines(t *testing.T) {
	source := `package example

func Run() {
	work()
	if true {
		cleanup()
		return
	}
	return
}
`

	expected := `package example

func Run() {
	work()

	if true {
		cleanup()

		return
	}

	return
}
`

	assertFormat(t, source, expected, IfSpacing, ReturnSpacing)
}
