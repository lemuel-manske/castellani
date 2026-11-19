package main

import (
	"flag"
	"fmt"
	"io"
	"os"
	"strings"

	"github.com/lemuel-manske/castellani/codemods/go/internal/runner"
	"github.com/lemuel-manske/castellani/codemods/go/rules"
)

func main() {
	os.Exit(run(os.Args[1:], os.Stdout, os.Stderr))
}

func run(args []string, stdout, stderr io.Writer) int {
	flags := flag.NewFlagSet("gofmtx", flag.ContinueOnError)
	flags.SetOutput(stderr)
	write := flags.Bool("w", false, "write changes to files")
	ruleNames := flags.String("rules", "declarations,types,spacing,returns,signatures,calls,structs,interfaces", "comma-separated rules")

	if err := flags.Parse(args); err != nil {
		return 2
	}

	theRules, err := selectRules(*ruleNames)
	if err != nil {
		fmt.Fprintln(stderr, err)
		return 2
	}

	changed, err := runner.Run(flags.Args(), *write, theRules...)
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

func selectRules(names string) ([]rules.Rule, error) {
	available := map[string]rules.Rule{
		"declarations": rules.DeclarationsOrder,
		"spacing":      rules.IfSpacing,
		"returns":      rules.ReturnSpacing,
		"structs":      rules.MultilineStructs,
		"types":        rules.TypeSpacing,
		"interfaces":   rules.InterfaceMethodSpacing,
		"signatures":   rules.MultilineSignatures,
		"calls":        rules.MultilineCalls,
	}

	var selected []rules.Rule
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
