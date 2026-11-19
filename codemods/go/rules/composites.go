package rules

import (
	"bytes"
	"go/ast"
	"go/format"
	"go/parser"
	"go/token"
)

// MultilineCompositeLiterals puts each keyed element on its own line,
// including nested literals. Positional elements are left unchanged.
// Literals with comments between elements are not rewritten.
func MultilineCompositeLiterals(source []byte) ([]byte, error) {
	set := token.NewFileSet()
	file, err := parser.ParseFile(set, "source.go", source, parser.ParseComments)
	if err != nil {
		return nil, err
	}

	var literals []*ast.CompositeLit
	ast.Inspect(file, func(node ast.Node) bool {
		literal, ok := node.(*ast.CompositeLit)
		if !ok || len(literal.Elts) == 0 {
			return true
		}

		for _, element := range literal.Elts {
			if _, ok := element.(*ast.KeyValueExpr); !ok {
				return true
			}
		}

		literals = append(literals, literal)
		return true
	})

	var edits []sourceEdit

	for _, literal := range literals {
		open := set.Position(literal.Lbrace).Offset
		close := set.Position(literal.Rbrace).Offset
		indent := lineIndent(source, open)

		// Inline nested literals need an additional indentation level for
		// every containing literal opened on the same source line.
		for _, outer := range literals {
			if outer == literal || outer.Lbrace >= literal.Lbrace || outer.Rbrace <= literal.Rbrace {
				continue
			}

			if set.Position(outer.Lbrace).Line == set.Position(literal.Lbrace).Line {
				indent += "\t"
			}
		}

		cursor := open + 1
		pending := make([]sourceEdit, 0, len(literal.Elts)+1)
		valid := true

		for i, element := range literal.Elts {
			start := set.Position(element.Pos()).Offset
			separator := source[cursor:start]

			if i == 0 {
				if len(bytes.TrimSpace(separator)) != 0 {
					valid = false
					break
				}
			} else {
				if !bytes.Equal(bytes.TrimSpace(separator), []byte(",")) {
					valid = false
					break
				}

				cursor += bytes.IndexByte(separator, ',') + 1
			}

			pending = append(pending, sourceEdit{
				start: cursor,
				end:   start,
				text:  "\n" + indent + "\t",
			})
			cursor = set.Position(element.End()).Offset
		}

		if !valid {
			continue
		}

		trailing := bytes.TrimSpace(source[cursor:close])
		if len(trailing) != 0 && !bytes.Equal(trailing, []byte(",")) {
			continue
		}

		pending = append(pending, sourceEdit{
			start: cursor,
			end:   close,
			text:  ",\n" + indent,
		})
		edits = append(edits, pending...)
	}

	if len(edits) == 0 {
		return source, nil
	}

	expanded, err := applyEdits(source, edits)
	if err != nil {
		return nil, err
	}

	// gofmt aligns the keys and fixes enclosing indentation after expanding
	// inline literals. The CLI runs this rule before the other layout rules.
	return format.Source(expanded)
}
