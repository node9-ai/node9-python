# CHANGELOG

<!-- version list -->

## v2.2.0 (2026-04-08)

### Bug Fixes

- Document and test that require_approval raise skips audit log
  ([`b5af150`](https://github.com/node9-ai/node9-python/commit/b5af1509963bffb5272fb2a94fb35a481360d720))

- Skip PR creation when dev has no new commits vs main
  ([`ebd3c50`](https://github.com/node9-ai/node9-python/commit/ebd3c50df7091fdae13377cdee1d2456c74db567))

- **evaluate**: Document @protect bypass, clarify TOCTOU safety; add SaaS path tests
  ([`2bd6400`](https://github.com/node9-ai/node9-python/commit/2bd6400e7631456fd0f2c448e3e61d5815b04647))

- **security**: Require_approval + offline now raises DaemonNotFoundError (fail-closed)
  ([`d6684f6`](https://github.com/node9-ai/node9-python/commit/d6684f6ff6f55def1ca01e728b6f7e41c38dbe78))

### Continuous Integration

- **auto-pr**: Clarify exit 0 intent with inline comment
  ([`2fab1c7`](https://github.com/node9-ai/node9-python/commit/2fab1c707dbd30c69042987ff6a770a51acc999e))

### Documentation

- **evaluate**: Document fail behaviour, auth, and timeouts; add public API import test
  ([`b9fcb17`](https://github.com/node9-ai/node9-python/commit/b9fcb17a0e9f683c638c77e3f5a6def2e64104c1))

### Features

- Export evaluate() as public API
  ([`6ecd581`](https://github.com/node9-ai/node9-python/commit/6ecd581af94db5aa1f0fa2a97ddc21a5300cb97f))

### Testing

- **evaluate**: Assert __all__ membership directly, document existing offline coverage
  ([`40d12bb`](https://github.com/node9-ai/node9-python/commit/40d12bb8b0d92266b180c1fa9fe6f729c2d3eb61))

- **saas**: Add denial path test; move assert_not_called inside with block
  ([`f44cff1`](https://github.com/node9-ai/node9-python/commit/f44cff124a8051131b3cddbe49cd11c7aa23c370))

- **saas**: Fix HTTPError mock, assert Bearer token, add run_id test; trim docstring
  ([`d5357ab`](https://github.com/node9-ai/node9-python/commit/d5357ab3c4f58a7cd120f185dfe8400b6af05ac0))


## v2.1.0 (2026-04-08)

### Bug Fixes

- Document and test that require_approval raise skips audit log
  ([#10](https://github.com/node9-ai/node9-python/pull/10),
  [`29fa9a7`](https://github.com/node9-ai/node9-python/commit/29fa9a707755d6c8880d729c23fa6ad8e89ce86e))

- Merge latest dev updates into main ([#10](https://github.com/node9-ai/node9-python/pull/10),
  [`29fa9a7`](https://github.com/node9-ai/node9-python/commit/29fa9a707755d6c8880d729c23fa6ad8e89ce86e))

- Skip PR creation when dev has no new commits vs main
  ([#10](https://github.com/node9-ai/node9-python/pull/10),
  [`29fa9a7`](https://github.com/node9-ai/node9-python/commit/29fa9a707755d6c8880d729c23fa6ad8e89ce86e))

- **evaluate**: Document @protect bypass, clarify TOCTOU safety; add SaaS path tests
  ([#10](https://github.com/node9-ai/node9-python/pull/10),
  [`29fa9a7`](https://github.com/node9-ai/node9-python/commit/29fa9a707755d6c8880d729c23fa6ad8e89ce86e))

- **security**: Require_approval + offline now raises DaemonNotFoundError (fail-closed)
  ([#10](https://github.com/node9-ai/node9-python/pull/10),
  [`29fa9a7`](https://github.com/node9-ai/node9-python/commit/29fa9a707755d6c8880d729c23fa6ad8e89ce86e))

### Continuous Integration

- **auto-pr**: Clarify exit 0 intent with inline comment
  ([#10](https://github.com/node9-ai/node9-python/pull/10),
  [`29fa9a7`](https://github.com/node9-ai/node9-python/commit/29fa9a707755d6c8880d729c23fa6ad8e89ce86e))

### Documentation

- **evaluate**: Document fail behaviour, auth, and timeouts; add public API import test
  ([#10](https://github.com/node9-ai/node9-python/pull/10),
  [`29fa9a7`](https://github.com/node9-ai/node9-python/commit/29fa9a707755d6c8880d729c23fa6ad8e89ce86e))

### Features

- Export evaluate() as public API ([#10](https://github.com/node9-ai/node9-python/pull/10),
  [`29fa9a7`](https://github.com/node9-ai/node9-python/commit/29fa9a707755d6c8880d729c23fa6ad8e89ce86e))

### Testing

- **evaluate**: Assert __all__ membership directly, document existing offline coverage
  ([#10](https://github.com/node9-ai/node9-python/pull/10),
  [`29fa9a7`](https://github.com/node9-ai/node9-python/commit/29fa9a707755d6c8880d729c23fa6ad8e89ce86e))

- **saas**: Add denial path test; move assert_not_called inside with block
  ([#10](https://github.com/node9-ai/node9-python/pull/10),
  [`29fa9a7`](https://github.com/node9-ai/node9-python/commit/29fa9a707755d6c8880d729c23fa6ad8e89ce86e))

- **saas**: Fix HTTPError mock, assert Bearer token, add run_id test; trim docstring
  ([#10](https://github.com/node9-ai/node9-python/pull/10),
  [`29fa9a7`](https://github.com/node9-ai/node9-python/commit/29fa9a707755d6c8880d729c23fa6ad8e89ce86e))


## v2.0.1 (2026-04-08)

### Bug Fixes

- Skip PR creation when dev has no new commits vs main
  ([#9](https://github.com/node9-ai/node9-python/pull/9),
  [`f3ae50d`](https://github.com/node9-ai/node9-python/commit/f3ae50d6b0f808114baece29f563dc2bbb9b09c1))


## v1.1.4 (2026-04-07)


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
