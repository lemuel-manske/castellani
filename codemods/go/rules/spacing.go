package rules

import (
	"go/ast"
	"go/parser"
	"go/token"
)

// IfSpacing separates an if statement from a preceding statement with exactly
// one blank line, unless the if is first in its containing block.
func IfSpacing(source []byte) ([]byte, error) {
	return separateStatements(source, false, func(previous, current ast.Stmt) bool {
		_, ok := current.(*ast.IfStmt)
		return ok
	})
}

// ReturnSpacing separates a return from any preceding statement in the same
// block or switch/select clause. Leading comments remain attached to returns,
// and the first statement in a block or clause is left unchanged.
func ReturnSpacing(source []byte) ([]byte, error) {
	return separateStatements(source, func(previous, current ast.Stmt) bool {
		_, ok := current.(*ast.ReturnStmt)
		return ok
	})
}

func separateStatements(source []byte, includeClauses bool, matches func(ast.Stmt, ast.Stmt) bool) ([]byte, error) {
	set := token.NewFileSet()
	file, err := parser.ParseFile(set, "source.go", source, parser.ParseComments)
	if err != nil {
		return nil, err
	}

	var edits []sourceEdit

	ast.Inspect(file, func(node ast.Node) bool {
		var statements []ast.Stmt

		switch block := node.(type) {
		case *ast.BlockStmt:
			statements = block.List
		case *ast.CaseClause:
			if !includeClauses {
				return true
			}
			statements = block.Body
		case *ast.CommClause:
			if !includeClauses {
				return true
			}
			statements = block.Body
		default:
			return true
		}

		for i := 1; i < len(statements); i++ {
			previous, current := statements[i-1], statements[i]
			if !matches(previous, current) {
				continue
			}

			addBlankLine(source, set, previous.End(), current.Pos(), &edits)
		}

		return true
	})

	return applyEdits(source, edits)
}

func addBlankLine(source []byte, set *token.FileSet, previousEnd, nextStart token.Pos, edits *[]sourceEdit) {
	start := set.Position(previousEnd).Offset
	end := set.Position(nextStart).Offset
	if start < 0 || end > len(source) || start > end || !whitespaceOnly(source[start:end]) {
		return
	}

	indent := lineIndent(source, end)
	replacement := "\n\n" + indent
	if string(source[start:end]) != replacement {
		*edits = append(*edits, sourceEdit{start: start, end: end, text: replacement})
	}
}
