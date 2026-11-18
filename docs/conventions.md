# Conventions

## Commands

Each service owns a `Makefile` as its documented command interface. Common development and verification tasks must be exposed through short, abstract targets such as `install`, `run`, `fmt`, `test`, and `check` instead of project-specific target names or raw tool commands. Makefiles do not contain explanatory comments; supporting documentation belongs in the service README.

## Go-specific conventions

### Style

Separate `require` and `assert` statements with a blank line whenever one follows the other.
