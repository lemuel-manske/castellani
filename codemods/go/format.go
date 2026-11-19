package codemods

import (
	"fmt"
	"go/format"
	"go/parser"
	"go/token"
)

// Rule rewrites Go source. A rule must be deterministic and idempotent.
type Rule func([]byte) ([]byte, error)

// Format applies the selected rules, in order, to canonical Go source.
// Rules may introduce layouts that gofmt cannot represent, so the output is
// checked for syntax but is not passed through gofmt a second time.
func Format(source []byte, rules ...Rule) ([]byte, error) {
	result, err := format.Source(source)
	if err != nil {
		return nil, fmt.Errorf("format source: %w", err)
	}

	for i, rule := range rules {
		if rule == nil {
			return nil, fmt.Errorf("rule %d is nil", i)
		}

		result, err = rule(result)
		if err != nil {
			return nil, fmt.Errorf("apply rule %d: %w", i, err)
		}

		if _, err := parser.ParseFile(token.NewFileSet(), "source.go", result, parser.ParseComments); err != nil {
			return nil, fmt.Errorf("rule %d produced invalid Go: %w", i, err)
		}
	}

	return result, nil
}
