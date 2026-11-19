package codemods

import (
	"bytes"
	"fmt"
	"sort"
)

type sourceEdit struct {
	start int
	end   int
	text  string
}

func applyEdits(source []byte, edits []sourceEdit) ([]byte, error) {
	sort.Slice(edits, func(i, j int) bool { return edits[i].start < edits[j].start })

	var output bytes.Buffer
	cursor := 0

	for _, edit := range edits {
		if edit.start < cursor || edit.end < edit.start || edit.end > len(source) {
			return nil, fmt.Errorf("overlapping or invalid edit at byte %d", edit.start)
		}

		output.Write(source[cursor:edit.start])
		output.WriteString(edit.text)
		cursor = edit.end
	}

	output.Write(source[cursor:])
	return output.Bytes(), nil
}

func whitespaceOnly(source []byte) bool {
	return len(bytes.TrimSpace(source)) == 0
}
