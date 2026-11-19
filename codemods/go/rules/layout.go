package rules

import (
	"bytes"
	"go/ast"
	"go/parser"
	"go/token"
)

// MultilineSignatures expands declarations with at least three parameter
// groups into one field per line. Declarations with comments in the parameter
// list are left unchanged to preserve comment attachment.
func MultilineSignatures(source []byte) ([]byte, error) {
	set := token.NewFileSet()
	file, err := parser.ParseFile(set, "source.go", source, parser.ParseComments)
	if err != nil {
		return nil, err
	}

	var edits []sourceEdit
	ast.Inspect(file, func(node ast.Node) bool {
		var params *ast.FieldList

		switch decl := node.(type) {
		case *ast.FuncDecl:
			params = decl.Type.Params
		case *ast.FuncLit:
			params = decl.Type.Params
		case *ast.Field:
			// Interface method signatures have no declaration of their own.
			if fn, ok := decl.Type.(*ast.FuncType); ok {
				params = fn.Params
			}
		}

		if params == nil || len(params.List) < 3 {
			return true
		}

		indent := lineIndent(source, set.Position(params.Opening).Offset)
		addListEdits(source, set, params.Opening, params.Closing, fieldPositions(params.List), indent, &edits)
		return true
	})

	return applyEdits(source, edits)
}

// MultilineCalls expands calls with at least three arguments. Calls containing
// comments between arguments are left unchanged rather than moving comments.
func MultilineCalls(source []byte) ([]byte, error) {
	set := token.NewFileSet()
	file, err := parser.ParseFile(set, "source.go", source, parser.ParseComments)
	if err != nil {
		return nil, err
	}

	var calls []*ast.CallExpr
	ast.Inspect(file, func(node ast.Node) bool {
		call, ok := node.(*ast.CallExpr)
		if ok && len(call.Args) >= 3 {
			calls = append(calls, call)
		}
		return true
	})

	var edits []sourceEdit
	for _, call := range calls {
		indent := lineIndent(source, set.Position(call.Lparen).Offset)
		for _, parent := range calls {
			if parent != call && parent.Pos() < call.Pos() && call.End() < parent.End() &&
				set.Position(parent.Lparen).Line == set.Position(call.Lparen).Line {
				indent += "\t"
			}
		}

		positions := make([]positionRange, len(call.Args))
		for i, arg := range call.Args {
			positions[i] = positionRange{start: arg.Pos(), end: arg.End()}
		}

		addListEdits(source, set, call.Lparen, call.Rparen, positions, indent, &edits)
	}

	return applyEdits(source, edits)
}

type positionRange struct {
	start token.Pos
	end   token.Pos
}

func fieldPositions(fields []*ast.Field) []positionRange {
	positions := make([]positionRange, len(fields))
	for i, field := range fields {
		positions[i] = positionRange{start: field.Pos(), end: field.End()}
	}
	return positions
}

func lineIndent(source []byte, offset int) string {
	start := bytes.LastIndexByte(source[:offset], '\n') + 1
	prefix := source[start:offset]
	i := 0
	for i < len(prefix) && (prefix[i] == ' ' || prefix[i] == '\t') {
		i++
	}
	return string(prefix[:i])
}

// addListEdits only touches whitespace after delimiters. Existing comma
// placement is detected from the source, not reconstructed from AST nodes.
func addListEdits(source []byte, set *token.FileSet, opening, closing token.Pos, items []positionRange, indent string, edits *[]sourceEdit) {
	if len(items) == 0 {
		return
	}

	open := set.Position(opening).Offset
	close := set.Position(closing).Offset
	if open < 0 || close > len(source) || open >= close {
		return
	}

	// If the argument list has comments or other non-whitespace tokens in
	// separator positions, skip the entire list rather than rewriting it.
	separators := make([]sourceEdit, 0, len(items)+1)
	start := open + 1
	for i, item := range items {
		end := set.Position(item.start).Offset
		separator := source[start:end]
		if i > 0 {
			trimmed := bytes.TrimSpace(separator)
			if !bytes.Equal(trimmed, []byte(",")) {
				return
			}
			// Preserve comma token; replace only whitespace after it.
			comma := bytes.IndexByte(separator, ',')
			start += comma + 1
		} else if !whitespaceOnly(separator) {
			return
		}

		separators = append(separators, sourceEdit{start: start, end: end, text: "\n" + indent + "\t"})
		start = set.Position(item.end).Offset
	}

	// A trailing comma may already be present. Include it when rewriting
	// the final gap; otherwise add one, as required by Go multiline syntax.
	last := source[start:close]
	trimmed := bytes.TrimSpace(last)
	if len(trimmed) > 0 && !bytes.Equal(trimmed, []byte(",")) {
		return
	}

	ending := ",\n" + indent
	separators = append(separators, sourceEdit{start: start, end: close, text: ending})
	*edits = append(*edits, separators...)
}
