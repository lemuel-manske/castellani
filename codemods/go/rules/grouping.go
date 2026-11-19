package rules

import (
	"go/ast"
	"go/parser"
	"go/token"
)

// StatementGrouping separates consecutive statements when a recognizable
// configuration phase begins or ends. It does not attempt to infer arbitrary
// business semantics from method names or variable references.
func StatementGrouping(source []byte) ([]byte, error) {
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
			statements := block.List
			if beginsConfiguration(statements, i) || endsConfiguration(statements, i) || changesObject(statements, i) || endsSetterGroup(statements, i) {
				addBlankLine(source, set, statements[i-1].End(), statements[i].Pos(), &edits)
			}
		}

		return true
	})

	return applyEdits(source, edits)
}

// A new variable followed by at least two consecutive field assignments
// begins a separate configuration phase.
func beginsConfiguration(statements []ast.Stmt, index int) bool {
	if index+1 >= len(statements) {
		return false
	}

	variable := definedVariable(statements[index-1])
	return variable != "" && fieldAssignmentRoot(statements[index]) == variable && fieldAssignmentRoot(statements[index+1]) == variable
}

// Two or more field assignments followed by a method call on the same object
// mark the transition from configuration to use.
func endsConfiguration(statements []ast.Stmt, index int) bool {
	if index < 2 {
		return false
	}

	root := fieldAssignmentRoot(statements[index-1])
	if root == "" || fieldAssignmentRoot(statements[index-2]) != root {
		return false
	}

	return statementCall(statements[index]).root == root
}

// Keep independent runs of field mutations visually distinct, without
// splitting a single continuous set of updates.
func changesObject(statements []ast.Stmt, index int) bool {
	if index < 2 || index+1 >= len(statements) {
		return false
	}

	previous := fieldAssignmentRoot(statements[index-1])
	current := fieldAssignmentRoot(statements[index])
	return previous != "" && current != "" && previous != current &&
		fieldAssignmentRoot(statements[index-2]) == previous &&
		fieldAssignmentRoot(statements[index+1]) == current
}

// A run of repeated setter invocations forms a cohesive configuration phase.
// Its next distinct operation begins a new paragraph.
func endsSetterGroup(statements []ast.Stmt, index int) bool {
	if index < 2 {
		return false
	}

	previous := statementCall(statements[index-1])
	before := statementCall(statements[index-2])
	if previous.name == "" || previous.name != before.name {
		return false
	}

	if previous.method != "Set" && previous.method != "Add" {
		return false
	}

	current := statementCall(statements[index])
	return current.name != "" && current.name != previous.name
}

func definedVariable(statement ast.Stmt) string {
	assignment, ok := statement.(*ast.AssignStmt)
	if !ok || assignment.Tok != token.DEFINE || len(assignment.Lhs) != 1 {
		return ""
	}

	identifier, ok := assignment.Lhs[0].(*ast.Ident)
	if !ok {
		return ""
	}
	return identifier.Name
}

func fieldAssignmentRoot(statement ast.Stmt) string {
	assignment, ok := statement.(*ast.AssignStmt)
	if !ok || assignment.Tok != token.ASSIGN || len(assignment.Lhs) != 1 {
		return ""
	}

	selector, ok := assignment.Lhs[0].(*ast.SelectorExpr)
	if !ok {
		return ""
	}
	return expressionRoot(selector.X)
}

// callIdentity captures only the receiver and invoked method, never arguments.
type callIdentity struct {
	name   string
	root   string
	method string
}

// statementCall recognizes direct method calls and calls returned by an
// assignment, without interpreting arbitrary expressions as operations.
func statementCall(statement ast.Stmt) callIdentity {
	var call *ast.CallExpr
	switch value := statement.(type) {
	case *ast.ExprStmt:
		call, _ = value.X.(*ast.CallExpr)
	case *ast.AssignStmt:
		if len(value.Rhs) == 1 {
			call, _ = value.Rhs[0].(*ast.CallExpr)
		}
	}
	if call == nil {
		return callIdentity{}
	}

	selector, ok := call.Fun.(*ast.SelectorExpr)
	if !ok {
		return callIdentity{}
	}

	receiver := expressionPath(selector.X)
	root := expressionRoot(selector.X)
	if receiver == "" || root == "" {
		return callIdentity{}
	}

	return callIdentity{
		name:   receiver + "." + selector.Sel.Name,
		root:   root,
		method: selector.Sel.Name,
	}
}

func expressionPath(expression ast.Expr) string {
	switch value := expression.(type) {
	case *ast.Ident:
		return value.Name
	case *ast.SelectorExpr:
		base := expressionPath(value.X)
		if base != "" {
			return base + "." + value.Sel.Name
		}
	case *ast.CallExpr:
		if len(value.Args) == 0 {
			base := expressionPath(value.Fun)
			if base != "" {
				return base + "()"
			}
		}
	}
	return ""
}

func expressionRoot(expression ast.Expr) string {
	switch value := expression.(type) {
	case *ast.Ident:
		return value.Name
	case *ast.SelectorExpr:
		return expressionRoot(value.X)
	case *ast.CallExpr:
		return expressionRoot(value.Fun)
	}
	return ""
}
