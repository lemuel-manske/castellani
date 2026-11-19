package rules

import (
	"bytes"
	"go/ast"
	"go/parser"
	"go/token"
)

// MultilineStructs expands nonempty structs written on a single line.
// It leaves empty structs and fields separated by comments unchanged.
func MultilineStructs(source []byte) ([]byte, error) {
	set := token.NewFileSet()
	file, err := parser.ParseFile(set, "source.go", source, parser.ParseComments)
	if err != nil {
		return nil, err
	}

	var edits []sourceEdit
	ast.Inspect(file, func(node ast.Node) bool {
		structType, ok := node.(*ast.StructType)
		if !ok || structType.Fields == nil || len(structType.Fields.List) == 0 {
			return true
		}

		fields := structType.Fields
		open := set.Position(fields.Opening).Offset
		close := set.Position(fields.Closing).Offset
		if set.Position(fields.Opening).Line != set.Position(fields.Closing).Line {
			return true
		}

		indent := lineIndent(source, open)
		start := open + 1
		var listEdits []sourceEdit

		for i, field := range fields.List {
			end := set.Position(field.Pos()).Offset
			separator := bytes.TrimSpace(source[start:end])

			if i == 0 {
				if len(separator) != 0 {
					return true
				}
			} else if !bytes.Equal(separator, []byte(";")) {
				// Preserve comments and other unsupported separators.
				return true
			}

			listEdits = append(listEdits, sourceEdit{
				start: start,
				end:   end,
				text:  "\n" + indent + "\t",
			})
			start = set.Position(field.End()).Offset
		}

		if !whitespaceOnly(source[start:close]) {
			return true
		}

		listEdits = append(listEdits, sourceEdit{
			start: start,
			end:   close,
			text:  "\n" + indent,
		})
		edits = append(edits, listEdits...)
		return true
	})

	return applyEdits(source, edits)
}
