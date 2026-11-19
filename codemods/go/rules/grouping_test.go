package rules

import "testing"

func TestFormat_HeaderSettersBeforeRequestExecution(t *testing.T) {
	source := `package example

func (c *Client) Run(request *Request, key string) {
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", key)
	data, err := c.execute(request, 201)
	_, _ = data, err
}
`

	expected := `package example

func (c *Client) Run(request *Request, key string) {
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", key)

	data, err := c.execute(request, 201)
	_, _ = data, err
}
`

	assertFormat(t, source, expected, StatementGrouping)
}

func TestFormat_InitializationBeforeFieldConfiguration(t *testing.T) {
	source := `package example

func (c *Client) Run(path, query string) {
	target := c.origin
	target.Path = path
	target.RawPath = ""
	target.RawQuery = query
}
`

	expected := `package example

func (c *Client) Run(path, query string) {
	target := c.origin

	target.Path = path
	target.RawPath = ""
	target.RawQuery = query
}
`

	assertFormat(t, source, expected, StatementGrouping)
}

func TestFormat_CommandConfigurationBeforeExecution(t *testing.T) {
	source := `package example

func Run() {
	cmd := NewCommand()
	cmd.Dir = "temp"
	cmd.Env = nil
	output, err := cmd.CombinedOutput()
	_, _ = output, err
}
`

	expected := `package example

func Run() {
	cmd := NewCommand()

	cmd.Dir = "temp"
	cmd.Env = nil

	output, err := cmd.CombinedOutput()
	_, _ = output, err
}
`

	assertFormat(t, source, expected, StatementGrouping)
}

func TestFormat_HeaderWriteAfterSetters(t *testing.T) {
	source := `package example

func Run(response *Response) {
	response.Header().Set("Content-Type", "application/json")
	response.Header().Set("Cache-Control", "no-store")
	response.WriteHeader(200)
}
`

	expected := `package example

func Run(response *Response) {
	response.Header().Set("Content-Type", "application/json")
	response.Header().Set("Cache-Control", "no-store")

	response.WriteHeader(200)
}
`

	assertFormat(t, source, expected, StatementGrouping)
}

func TestFormat_IndependentFieldMutationGroups(t *testing.T) {
	source := `package example

func Run(client *Client, server *Server) {
	client.Timeout = 10
	client.Transport = nil
	server.ReadTimeout = 10
	server.WriteTimeout = 20
}
`

	expected := `package example

func Run(client *Client, server *Server) {
	client.Timeout = 10
	client.Transport = nil

	server.ReadTimeout = 10
	server.WriteTimeout = 20
}
`

	assertFormat(t, source, expected, StatementGrouping)
}

func TestFormat_NumericComputationRemainsContinuous(t *testing.T) {
	source := `package example

func Run(multiplier int) {
	count := 0
	count++
	count += 2
	count *= multiplier
}
`

	assertFormat(t, source, source, StatementGrouping)
}

func TestFormat_UnrelatedCallsRemainUnchanged(t *testing.T) {
	source := `package example

func Run(client *Client) {
	client.Connect()
	client.Send(nil)
	client.Close()
}
`

	assertFormat(t, source, source, StatementGrouping)
}

func TestFormat_CommentsRemainAttachedToStatements(t *testing.T) {
	source := `package example

func Run(request *Request) {
	request.Header.Set("One", "1")
	request.Header.Set("Two", "2")
	// Preserve this explanation.
	request.Execute()
}
`

	assertFormat(t, source, source, StatementGrouping)
}

func TestFormat_ExistingGroupingIsPreserved(t *testing.T) {
	source := `package example

func Run(request *Request) {
	request.Header.Set("One", "1")
	request.Header.Set("Two", "2")

	request.Execute()
}
`

	assertFormat(t, source, source, StatementGrouping)
}
