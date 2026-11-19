package codemods

import "testing"

func TestFormat_ConstantsBeforeTypes(t *testing.T) {
	source := `package example

type Service struct {
	Name string
}

func NewService() Service {
	return Service{}
}

const DefaultName = "service"
`

	expected := `package example

const DefaultName = "service"

type Service struct {
	Name string
}

func NewService() Service {
	return Service{}
}
`

	assertFormat(t, source, expected, DeclarationsOrder)
}

func TestFormat_AlreadyOrdered_RemainsUnchanged(t *testing.T) {
	source := `package example

const DefaultName = "service"

type Service struct{}

func NewService() Service {
	return Service{}
}
`

	assertFormat(t, source, source, DeclarationsOrder)
}

func TestFormat_DeclarationComments_MoveWithTheirDeclarations(t *testing.T) {
	source := `package example

// Service stores the name.
type Service struct{}

// DefaultName names the service.
const DefaultName = "service"
`

	expected := `package example

// DefaultName names the service.
const DefaultName = "service"

// Service stores the name.
type Service struct{}
`

	assertFormat(t, source, expected, DeclarationsOrder)
}

func TestFormat_DeclarationOrder_PreservesMethodGrouping(t *testing.T) {
	source := `package example

type Service struct{}

func (Service) Run() {}

const DefaultName = "service"
`

	expected := `package example

const DefaultName = "service"

type Service struct{}

func (Service) Run() {}
`

	assertFormat(t, source, expected, DeclarationsOrder)
}

func TestFormat_DetachedComments_ReturnsError(t *testing.T) {
	source := `package example

type Service struct{}

// An unrelated note.

const DefaultName = "service"
`

	assertFormatError(t, source, DeclarationsOrder)
}

func TestFormat_ImportsRemainBeforeDeclarations(t *testing.T) {
	source := `package example

import "context"

type Service struct {
	Context context.Context
}

const DefaultName = "service"
`

	expected := `package example

import "context"

const DefaultName = "service"

type Service struct {
	Context context.Context
}
`

	assertFormat(t, source, expected, DeclarationsOrder)
}

func TestFormat_ConstantsBeforeVariables_PreservesInitializerOrder(t *testing.T) {
	source := `package example

var first = initialize(1)

type Service struct{}

const DefaultName = "service"

var second = initialize(2)

func initialize(n int) int { return n }
`

	expected := `package example

const DefaultName = "service"

var first = initialize(1)

var second = initialize(2)

type Service struct{}

func initialize(n int) int { return n }
`

	assertFormat(t, source, expected, DeclarationsOrder)
}

func TestFormat_MultipleInitFunctions_PreserveOrder(t *testing.T) {
	source := `package example

func init() { println("first") }

type Service struct{}

const Name = "example"

func init() { println("second") }
`

	expected := `package example

const Name = "example"

func init() { println("first") }

type Service struct{}

func init() { println("second") }
`

	assertFormat(t, source, expected, DeclarationsOrder)
}

func TestFormat_DeclarationOrdering_PreservesBuildConstraints(t *testing.T) {
	source := `//go:build linux

package example

type Service struct{}

const Name = "example"
`

	expected := `//go:build linux

package example

const Name = "example"

type Service struct{}
`

	assertFormat(t, source, expected, DeclarationsOrder)
}
