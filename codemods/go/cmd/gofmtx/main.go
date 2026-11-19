package main

import (
	"flag"
	"fmt"
	"io"
	"os"
	"strings"

	codemods "github.com/lemuel-manske/castellani/codemods/go"
	"github.com/lemuel-manske/castellani/codemods/go/internal/runner"
)

func main() {
	os.Exit(run(os.Args[1:], os.Stdout, os.Stderr))
}

func run(args []string, stdout, stderr io.Writer) int {
	flags := flag.NewFlagSet("gofmtx", flag.ContinueOnError)
	flags.SetOutput(stderr)
	write := flags.Bool("w", false, "write changes to files")
	ruleNames := flags.String("rules", "declarations,spacing,signatures,calls", "comma-separated rules")

	if err := flags.Parse(args); err != nil {
		return 2
	}

	rules, err := selectRules(*ruleNames)
	if err != nil {
		fmt.Fprintln(stderr, err)
		return 2
	}

	changed, err := runner.Run(flags.Args(), *write, rules...)
	if err != nil {
		fmt.Fprintln(stderr, err)
		return 2
	}

	for _, path := range changed {
		fmt.Fprintln(stdout, path)
	}

	if !*write && len(changed) > 0 {
		return 1
	}
	return 0
}

func selectRules(names string) ([]codemods.Rule, error) {
	available := map[string]codemods.Rule{
		"declarations": codemods.DeclarationsOrder,
		"spacing":      codemods.IfSpacing,
		"signatures":   codemods.MultilineSignatures,
		"calls":        codemods.MultilineCalls,
	}

	var selected []codemods.Rule
	seen := make(map[string]bool)
	for _, name := range strings.Split(names, ",") {
		name = strings.TrimSpace(name)
		if name == "" {
			return nil, fmt.Errorf("empty rule name")
		}
		if seen[name] {
			return nil, fmt.Errorf("duplicate rule %q", name)
		}
		rule, ok := available[name]
		if !ok {
			return nil, fmt.Errorf("unknown rule %q", name)
		}
		seen[name] = true
		selected = append(selected, rule)
	}
	return selected, nil
}
