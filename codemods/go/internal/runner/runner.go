package runner

import (
	"bytes"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"

	codemods "github.com/lemuel-manske/castellani/codemods/go"
)

// Run formats the selected files. In check mode it reports changes without
// writing. In write mode every changed file is replaced atomically.
func Run(paths []string, write bool, rules ...codemods.Rule) ([]string, error) {
	files, err := collect(paths)
	if err != nil {
		return nil, err
	}

	var changed []string
	pending := make(map[string][]byte)

	for _, path := range files {
		original, err := os.ReadFile(path)
		if err != nil {
			return changed, fmt.Errorf("read %s: %w", path, err)
		}

		if isGenerated(original) {
			continue
		}

		formatted, err := codemods.Format(original, rules...)
		if err != nil {
			return changed, fmt.Errorf("format %s: %w", path, err)
		}

		if bytes.Equal(original, formatted) {
			continue
		}

		pending[path] = formatted
		changed = append(changed, path)
	}

	// Finish validation before writing any file. A failed parse or rule
	// must not leave earlier files modified.
	if write {
		for _, path := range changed {
			if err := replace(path, pending[path]); err != nil {
				return changed, fmt.Errorf("write %s: %w", path, err)
			}
		}
	}

	return changed, nil
}

func collect(paths []string) ([]string, error) {
	if len(paths) == 0 {
		paths = []string{"."}
	}

	found := make(map[string]struct{})

	for _, root := range paths {
		info, err := os.Lstat(root)
		if err != nil {
			return nil, fmt.Errorf("stat %s: %w", root, err)
		}

		if info.Mode().IsRegular() {
			if filepath.Ext(root) != ".go" {
				return nil, fmt.Errorf("not a Go file: %s", root)
			}
			found[filepath.Clean(root)] = struct{}{}
			continue
		}

		if !info.IsDir() {
			return nil, fmt.Errorf("not a regular file or directory: %s", root)
		}

		err = filepath.WalkDir(root, func(path string, entry fs.DirEntry, walkErr error) error {
			if walkErr != nil {
				return walkErr
			}

			if entry.IsDir() {
				if path != root && skipDirectory(entry.Name()) {
					return filepath.SkipDir
				}
				return nil
			}

			if entry.Type().IsRegular() && filepath.Ext(path) == ".go" {
				found[filepath.Clean(path)] = struct{}{}
			}

			return nil
		})
		if err != nil {
			return nil, fmt.Errorf("walk %s: %w", root, err)
		}
	}

	files := make([]string, 0, len(found))
	for path := range found {
		files = append(files, path)
	}
	sort.Strings(files)
	return files, nil
}

func skipDirectory(name string) bool {
	return name == "vendor" || name == "testdata" || strings.HasPrefix(name, ".")
}

func isGenerated(source []byte) bool {
	for _, line := range bytes.SplitN(source, []byte("\n"), 30) {
		if bytes.Contains(line, []byte("Code generated")) && bytes.Contains(line, []byte("DO NOT EDIT.")) {
			return true
		}
	}
	return false
}

func replace(path string, content []byte) (err error) {
	info, err := os.Stat(path)
	if err != nil {
		return err
	}

	file, err := os.CreateTemp(filepath.Dir(path), ".codemod-*")
	if err != nil {
		return err
	}
	defer os.Remove(file.Name())

	if err := file.Chmod(info.Mode().Perm()); err != nil {
		file.Close()
		return err
	}
	if _, err := file.Write(content); err != nil {
		file.Close()
		return err
	}
	if err := file.Close(); err != nil {
		return err
	}
	return os.Rename(file.Name(), path)
}
