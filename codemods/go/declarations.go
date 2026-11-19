package codemods

import (
	"bytes"
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"sort"
)

// DeclarationsOrder places package-level constants before variables, types,
// and functions without changing the order inside each category. Existing
// type/function interleaving is retained so methods stay near their types.
// Import declarations are never moved.
func DeclarationsOrder(source []byte) ([]byte, error) {
	fset := token.NewFileSet()
	file, err := parser.ParseFile(fset, "source.go", source, parser.ParseComments)
	if err != nil {
		return nil, err
	}

	first := 0
	for first < len(file.Decls) && isImport(file.Decls[first]) {
		first++
	}

	if first == len(file.Decls) {
		return source, nil
	}

	decls := file.Decls[first:]
	ordered := append([]ast.Decl(nil), decls...)
	sort.SliceStable(ordered, func(i, j int) bool {
		return declarationRank(ordered[i]) < declarationRank(ordered[j])
	})

	changed := false
	for i := range decls {
		if decls[i] != ordered[i] {
			changed = true
			break
		}
	}

	if !changed {
		return source, nil
	}

	starts := make([]int, len(decls))
	for i, decl := range decls {
		starts[i] = fset.PositionFor(declarationStart(decl), false).Offset
	}

	// Detached comments between declarations cannot be assigned to a
	// declaration unambiguously. Refuse to move them rather than misplace them.
	for i, decl := range decls {
		end := fset.PositionFor(decl.End(), false).Offset
		limit := len(source)
		if i+1 < len(decls) {
			limit = starts[i+1]
		}

		for _, comment := range file.Comments {
			pos := fset.PositionFor(comment.Pos(), false).Offset
			if pos >= end && pos < limit {
				return nil, fmt.Errorf("cannot reorder detached comment at line %d", fset.Position(comment.Pos()).Line)
			}
		}
	}

	parts := make(map[ast.Decl][]byte, len(decls))
	for i, decl := range decls {
		end := len(source)
		if i+1 < len(decls) {
			end = starts[i+1]
		}
		parts[decl] = bytes.TrimSpace(source[starts[i]:end])
	}

	var out bytes.Buffer
	out.Write(bytes.TrimRight(source[:starts[0]], " \t\n\r"))
	out.WriteString("\n\n")

	for i, decl := range ordered {
		if i > 0 {
			out.WriteString("\n\n")
		}
		out.Write(parts[decl])
	}
	out.WriteByte('\n')

	return out.Bytes(), nil
}

func declarationStart(decl ast.Decl) token.Pos {
	switch d := decl.(type) {
	case *ast.GenDecl:
		if d.Doc != nil {
			return d.Doc.Pos()
		}
	case *ast.FuncDecl:
		if d.Doc != nil {
			return d.Doc.Pos()
		}
	}

	return decl.Pos()
}

func isImport(decl ast.Decl) bool {
	gen, ok := decl.(*ast.GenDecl)
	return ok && gen.Tok == token.IMPORT
}

func declarationRank(decl ast.Decl) int {
	gen, ok := decl.(*ast.GenDecl)
	if !ok {
		return 2
	}

	switch gen.Tok {
	case token.CONST:
		return 0
	case token.VAR:
		return 1
	default:
		return 2
	}
}
