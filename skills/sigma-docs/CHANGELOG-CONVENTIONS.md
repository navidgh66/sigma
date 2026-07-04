# Changelog conventions

Reference for `sigma-docs`' CHANGELOG mode. Focused reference, not a second
`SKILL.md`.

## Prefix → section mapping

| Prefix | Section |
|--------|---------|
| `feat` | Added |
| `fix` | Fixed |
| `perf` | Performance |
| `refactor` / `chore` | Changed (omit `chore` from external-facing notes unless user-visible) |
| `docs` | Documentation |
| `ci` / `test` | omit from external release notes (internal-only) |

If a commit message doesn't follow conventional-commit style, read the diff
summary and place it in the closest matching section rather than inventing a
prefix.

## Git recipes

```bash
# Commits since the last release tag
git log --oneline vX..HEAD

# Find the last release tag (most recent first)
git tag --sort=-creatordate

# Keep commit hashes for traceability
git log --pretty=format:"%s (%h)"
```

Combine the last two to find the range automatically:

```bash
LAST_TAG=$(git tag --sort=-creatordate | head -1)
git log --pretty=format:"%s (%h)" "${LAST_TAG}..HEAD"
```

## Keep-a-Changelog format skeleton

```markdown
## [version] - YYYY-MM-DD

### Added
- one bullet per `feat` commit, referencing the commit message/hash

### Changed
- one bullet per `refactor`/user-visible `chore` commit

### Fixed
- one bullet per `fix` commit

### Performance
- one bullet per `perf` commit

### Documentation
- one bullet per `docs` commit
```

Omit any section with zero commits in the range — don't emit empty headers.

## Hard rule

Map every changelog entry to a real commit hash or message — never invent an
entry.
