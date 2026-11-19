package rules

import (
	"go/ast"
	"go/parser"
	"go/token"
)

// IfSpacing separates an if statement from a preceding statement with exactly
// one blank line, unless the if is first in its containing block.
func IfSpacing(source []byte) ([]byte, error) {
	return separateStatements(source, func(previous, current ast.Stmt) bool {
		_, ok := current.(*ast.IfStmt)
		return ok
	})
}

// ReturnSpacing separates a return from a preceding if statement. Returns
// inside the if body and returns following comments are left unchanged.
func ReturnSpacing(source []byte) ([]byte, error) {
	return separateStatements(source, func(previous, current ast.Stmt) bool {
		_, isIf := previous.(*ast.IfStmt)
		_, isReturn := current.(*ast.ReturnStmt)
		return isIf && isReturn
	})
}

func separateStatements(source []byte, matches func(ast.Stmt, ast.Stmt) bool) ([]byte, error) {
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
			previous, current := block.List[i-1], block.List[i]
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
