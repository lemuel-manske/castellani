package main

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestCLI_CheckAndWriteWorkflow(t *testing.T) {
	path := filepath.Join(t.TempDir(), "example.go")

	source := "package example\n\ntype Service struct{}\n\nconst Name = \"example\"\n"
	if err := os.WriteFile(path, []byte(source), 0o644); err != nil {
		t.Fatal(err)
	}

	var stdout, stderr bytes.Buffer
	code := run([]string{"-rules", "declarations", path}, &stdout, &stderr)
	if code != 1 || !strings.Contains(stdout.String(), path) || stderr.Len() != 0 {
		t.Fatalf("check: code=%d stdout=%q stderr=%q", code, stdout.String(), stderr.String())
	}

	stdout.Reset()
	code = run([]string{"-w", "-rules", "declarations", path}, &stdout, &stderr)
	if code != 0 || !strings.Contains(stdout.String(), path) || stderr.Len() != 0 {
		t.Fatalf("write: code=%d stdout=%q stderr=%q", code, stdout.String(), stderr.String())
	}

	stdout.Reset()
	code = run([]string{"-rules", "declarations", path}, &stdout, &stderr)
	if code != 0 || stdout.Len() != 0 || stderr.Len() != 0 {
		t.Fatalf("stable check: code=%d stdout=%q stderr=%q", code, stdout.String(), stderr.String())
	}
}

func TestCLI_UnknownRuleIsRejected(t *testing.T) {
	var stdout, stderr bytes.Buffer

	code := run([]string{"-rules", "unknown"}, &stdout, &stderr)
	if code != 2 || !strings.Contains(stderr.String(), "unknown rule") {
		t.Fatalf("expected rule selection error, got code=%d stderr=%q", code, stderr.String())
	}
}

func TestCLI_DuplicateRuleIsRejected(t *testing.T) {
	var stdout, stderr bytes.Buffer

	code := run([]string{"-rules", "spacing,spacing"}, &stdout, &stderr)
	if code != 2 || !strings.Contains(stderr.String(), "duplicate rule") {
		t.Fatalf("expected duplicate rule error, got code=%d stderr=%q", code, stderr.String())
	}
}
