package codemods

import (
	"go/ast"
	"go/parser"
	"go/token"
)

// IfSpacing separates an if statement from the preceding statement with
// exactly one blank line, unless the if is first in its block. Comments are
// left untouched rather than being moved away from the statement they explain.
func IfSpacing(source []byte) ([]byte, error) {
	set := token.NewFileSet()
	file, err := parser.ParseFile(set, "source.go", source, parser.ParseComments)
	if err != nil {
		return nil, err
	}

	var edits []sourceEdit

	ast.Inspect(file, func(node ast.Node) bool {
		block, ok := node.(*ast.BlockStmt)
		if !ok {
			return true
		}

		for i := 1; i < len(block.List); i++ {
			statement, ok := block.List[i].(*ast.IfStmt)
			if !ok {
				continue
			}

			previous := block.List[i-1]
			start := set.Position(previous.End()).Offset
			end := set.Position(statement.Pos()).Offset
			between := source[start:end]
			if !whitespaceOnly(between) {
				continue
			}

			// Match the indentation of the existing if statement.
			indentStart := end
			for indentStart > 0 && source[indentStart-1] != '\n' {
				indentStart--
			}
			indent := source[indentStart:end]
			if !whitespaceOnly(indent) {
				continue
			}

			replacement := "\n\n" + string(indent)
			if string(between) != replacement {
				edits = append(edits, sourceEdit{start: start, end: end, text: replacement})
			}
		}

		return true
	})

	return applyEdits(source, edits)
}
