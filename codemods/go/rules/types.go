package rules

import (
	"go/ast"
	"go/parser"
	"go/token"
)

// TypeSpacing separates consecutive top-level type declarations.
// Comments between declarations are preserved without relocation.
func TypeSpacing(source []byte) ([]byte, error) {
	set := token.NewFileSet()
	file, err := parser.ParseFile(set, "source.go", source, parser.ParseComments)
	if err != nil {
		return nil, err
	}

	var edits []sourceEdit
	for i := 1; i < len(file.Decls); i++ {
		previous, current := file.Decls[i-1], file.Decls[i]
		if !isTypeDeclaration(previous) || !isTypeDeclaration(current) {
			continue
		}
		addBlankLine(source, set, previous.End(), current.Pos(), &edits)
	}

	return applyEdits(source, edits)
}

// InterfaceMethodSpacing separates adjacent interface members with a blank
// line. Attached method comments and embedded interfaces remain in place.
func InterfaceMethodSpacing(source []byte) ([]byte, error) {
	set := token.NewFileSet()
	file, err := parser.ParseFile(set, "source.go", source, parser.ParseComments)
	if err != nil {
		return nil, err
	}

	var edits []sourceEdit
	ast.Inspect(file, func(node ast.Node) bool {
		iface, ok := node.(*ast.InterfaceType)
		if !ok || iface.Methods == nil {
			return true
		}

		fields := iface.Methods.List
		for i := 1; i < len(fields); i++ {
			addBlankLine(source, set, fields[i-1].End(), fields[i].Pos(), &edits)
		}
		return true
	})

	return applyEdits(source, edits)
}

func isTypeDeclaration(decl ast.Decl) bool {
	gen, ok := decl.(*ast.GenDecl)
	return ok && gen.Tok == token.TYPE
}
