function isConditionalCheckFailure(error: unknown): boolean {
  return (
    error instanceof Error && error.name === "ConditionalCheckFailedException"
  );
}

export { isConditionalCheckFailure };
