# CHANGELOG

<!-- version list -->

## v2.0.0 (2026-04-07)

### Breaking Changes

- **`Node9Agent`** base class introduced — framework-agnostic governed agent with `@tool`, `@internal`, `dispatch()`, `build_tools_anthropic()`, `build_tools_openai()`
- **`safe_path(filename, workspace=...)`** — `workspace` is now keyword-only (prevents silent arg swap)
- **`configure()`** — replaces direct env-var mutation; thread-safe via `threading.RLock`

### New Features

- `Node9Agent`: zero-dependency governed agent base class with DLP, path safety, and audit built-in
- `@tool` decorator: DLP scan + path traversal check + `evaluate()` on every call
- `@internal` decorator: infrastructure methods (no governance); warns if applied to a public method
- `dispatch()`: LLM-safe router — always returns `str`, handles async tools, unknown tools return descriptive error
- `build_tools_anthropic()` / `build_tools_openai()`: auto-generate tool specs from type annotations
- `new_session()`: fresh `run_id` for server/multi-session deployments
- Offline mode warns loudly when `policy=require_approval` but no daemon/API key is available
- `NODE9_SKIP=1` emits `warnings.warn()` at import time AND per `evaluate()` call
- All SDK status output moved to stderr (stdout stays clean for LLM tool parsers)

### Migration from 1.x

```python
# Before (1.x) — positional workspace arg
safe_path(filename, workspace_dir)

# After (2.0) — keyword-only
safe_path(filename, workspace=workspace_dir)
```

`@protect` and `configure()` are fully backwards-compatible. Only `safe_path` call sites need updating.

## v1.0.0 (2026-04-04)

- Initial Release

## v1.1.0 (2026-03-15)

### Features

- Add Gemini AI code review on PRs to main
  ([`50b651d`](https://github.com/node9-ai/node9-python/commit/50b651dc2575dc954def69dd16d7492369a8149a))

- Switch AI code review from Gemini to Claude Sonnet
  ([`c52fbb4`](https://github.com/node9-ai/node9-python/commit/c52fbb4ee5d1b460ef008b708e3664e0650f93f9))


## v1.0.3 (2026-03-15)

### Bug Fixes

- Install twine before upload step
  ([`4b4e142`](https://github.com/node9-ai/node9-python/commit/4b4e142b02815937551cbbb8569aa72b0ab222bc))


## v1.0.2 (2026-03-15)

### Bug Fixes

- Publish to PyPI explicitly with twine instead of semantic-release publish
  ([`6847fdb`](https://github.com/node9-ai/node9-python/commit/6847fdbbf6c0bbd7a14a743b99745cdf005d73a9))


## v1.0.1 (2026-03-15)

### Bug Fixes

- Add TWINE credentials and twine to build command for PyPI upload
  ([`d71d73d`](https://github.com/node9-ai/node9-python/commit/d71d73d1caa3c05cfd5011edcd3913f5fc976d07))


## v1.0.0 (2026-03-15)

- Initial Release
