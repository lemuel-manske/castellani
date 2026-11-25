package rabbitmq

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"sync"

	"github.com/santhosh-tekuri/jsonschema/v6"
)

var validators = sync.OnceValues(loadValidators)

func Validate(data []byte) (string, error) {
	messageValidators, err := validators()

	if err != nil {
		return "", err
	}

	var envelope struct {
		Type string `json:"type"`
	}

	if err = json.Unmarshal(data, &envelope); err != nil {
		return "", fmt.Errorf("decode message: %w", err)
	}

	validator, ok := messageValidators[envelope.Type]

	if !ok {
		return "", fmt.Errorf("unsupported message type %q", envelope.Type)
	}

	instance, err := jsonschema.UnmarshalJSON(bytes.NewReader(data))

	if err != nil {
		return "", fmt.Errorf("decode message: %w", err)
	}

	if err := validator.Validate(instance); err != nil {
		return "", fmt.Errorf("validate %s message: %w", envelope.Type, err)
	}

	return envelope.Type, nil
}

func loadValidators() (map[string]*jsonschema.Schema, error) {
	compiler := jsonschema.NewCompiler()
	compiler.AssertFormat()

	files, err := contractFiles()

	if err != nil {
		return nil, err
	}

	resources := make(map[string]any, len(files))
	urls := make(map[string]string, len(files))

	for _, path := range files {
		resourceURL, err := fileURL(path)

		if err != nil {
			return nil, err
		}

		document, err := readSchema(path)

		if err != nil {
			return nil, err
		}

		if err := compiler.AddResource(resourceURL, document); err != nil {
			return nil, fmt.Errorf("add contract %s: %w", path, err)
		}

		resources[path] = document
		urls[path] = resourceURL
	}

	result := make(map[string]*jsonschema.Schema, len(files))

	for _, path := range files {
		messageType := schemaMessageType(resources[path])

		if messageType == "" {
			continue
		}

		schema, err := compiler.Compile(urls[path])

		if err != nil {
			return nil, fmt.Errorf("compile contract %s: %w", path, err)
		}

		result[messageType] = schema
	}

	return result, nil
}

func contractFiles() ([]string, error) {
	root := os.Getenv("CONTRACTS_DIR")

	if root == "" {
		return nil, errors.New("CONTRACTS_DIR is not set")
	}

	entries, err := os.ReadDir(filepath.Join(root, "messages"))

	if err != nil {
		return nil, fmt.Errorf("read message contracts: %w", err)
	}

	files := []string{filepath.Join(root, "archive-manifest.v1.schema.json")}

	for _, entry := range entries {
		if strings.HasSuffix(entry.Name(), ".v1.schema.json") {
			files = append(files, filepath.Join(root, "messages", entry.Name()))
		}
	}

	return files, nil
}

func fileURL(path string) (string, error) {
	absolute, err := filepath.Abs(path)

	if err != nil {
		return "", fmt.Errorf("resolve contract %s: %w", path, err)
	}

	return (&url.URL{Scheme: "file", Path: filepath.ToSlash(absolute)}).String(), nil
}

func readSchema(path string) (any, error) {
	file, err := os.Open(path)

	if err != nil {
		return nil, fmt.Errorf("open contract %s: %w", path, err)
	}

	defer file.Close()

	document, err := jsonschema.UnmarshalJSON(file)

	if err != nil {
		return nil, fmt.Errorf("decode contract %s: %w", path, err)
	}

	return document, nil
}

func schemaMessageType(document any) string {
	root, ok := document.(map[string]any)

	if !ok {
		return ""
	}

	properties, ok := root["properties"].(map[string]any)

	if !ok {
		return ""
	}

	messageType, ok := properties["type"].(map[string]any)

	if !ok {
		return ""
	}

	constant, _ := messageType["const"].(string)

	return constant
}
