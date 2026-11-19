package rules

import "testing"

func TestFormat_AdjacentTypeDeclarations_HaveBlankLine(t *testing.T) {
	source := `package example

type WACZ struct {
	Body bool
}
type Capture interface {
	GetSnapshot() error
}
`

	expected := `package example

type WACZ struct {
	Body bool
}

type Capture interface {
	GetSnapshot() error
}
`

	assertFormat(t, source, expected, TypeSpacing)
}

func TestFormat_AdjacentInterfaceMethods_HaveBlankLines(t *testing.T) {
	source := `package example

type Capture interface {
	GetSnapshot() error
	SaveSnapshot() error
	DeleteSnapshot() error
}
`

	expected := `package example

type Capture interface {
	GetSnapshot() error

	SaveSnapshot() error

	DeleteSnapshot() error
}
`

	assertFormat(t, source, expected, InterfaceMethodSpacing)
}

func TestFormat_InterfaceMethods_WithComments_KeepComments(t *testing.T) {
	source := `package example

type Capture interface {
	GetSnapshot() error
	// SaveSnapshot persists data.
	SaveSnapshot() error
}
`

	assertFormat(t, source, source, InterfaceMethodSpacing)
}

func TestFormat_TypeSpacing_WithComments_PreservesAttachedDocumentation(t *testing.T) {
	source := `package example

type WACZ struct{}
// Capture describes the reader.
type Capture interface {
	GetSnapshot() error
}
`

	expected := `package example

type WACZ struct{}

// Capture describes the reader.
type Capture interface {
	GetSnapshot() error
}
`

	assertFormat(t, source, expected, TypeSpacing)
}

func TestFormat_CombinedTypeAndInterfaceSpacing(t *testing.T) {
	source := `package example

type WACZ struct {
	Body bool
}
type Capture interface {
	GetSnapshot() error
	SaveSnapshot() error
}
`

	expected := `package example

type WACZ struct {
	Body bool
}

type Capture interface {
	GetSnapshot() error

	SaveSnapshot() error
}
`

	assertFormat(t, source, expected, TypeSpacing, InterfaceMethodSpacing)
}

func TestFormat_AlreadySeparatedTypesAndMethods_RemainUnchanged(t *testing.T) {
	source := `package example

type WACZ struct {
	Body bool
}

type Capture interface {
	GetSnapshot() error

	SaveSnapshot() error
}
`

	assertFormat(t, source, source, TypeSpacing, InterfaceMethodSpacing)
}
