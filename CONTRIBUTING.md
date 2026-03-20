# Contributing to Rigel

Thank you for your interest in contributing to Rigel! This document provides guidelines and
information for contributors.

## Getting Started

1. Fork the repository
2. Create a feature branch from `main`
3. Make your changes
4. Submit a pull request

## What Can I Contribute?

Rigel is in active development. Here are some ways to contribute:

- **Language design feedback** — Open an issue to discuss design ideas or trade-offs
- **Specification improvements** — Clarify wording, fix examples, or fill in gaps in
  `docs/rigel-spec.md`
- **Compiler/interpreter development** — Bug fixes, new features, performance improvements
- **Test cases** — Add tests that exercise language features or edge cases
- **Documentation** — Tutorials, examples, and explanations

## Development Guidelines

### Code Style

- Wrap lines at 120 characters
- Use four spaces for indentation (unless the language requires otherwise)
- Rigel source files use the `.rgl` extension

### Commit Messages

- Use imperative mood: "Add feature", not "Added feature"
- Keep the subject line under 72 characters
- Include context in the body when the change isn't self-explanatory

### Pull Requests

- Keep PRs focused — one logical change per PR
- Include a clear description of what the change does and why
- Reference any related issues
- Ensure all tests pass before submitting

## Design Discussions

Rigel's design is driven by its specification (`docs/rigel-spec.md`). If you want to propose a
language-level change:

1. Open an issue describing the proposal
2. Reference relevant prior art (Scheme, Clojure, Rust, C++, PL theory)
3. Include concrete Rigel syntax examples
4. Consider compilation/implementation implications

## Reporting Bugs

When reporting bugs, please include:

- Steps to reproduce the issue
- Expected behavior
- Actual behavior
- Platform and version information

## License

By contributing to Rigel, you agree that your contributions will be licensed under the
[MIT License](LICENSE).
