# Contributing 
# EXAMPLE <._________________________________.>

## Branches
- Use `feature-<short-name>` or `fix-<short-name>`.

## Commits
- Use clear, descriptive messages (e.g., "Add login form validation").

## Style (C++)
- 2 or 4 spaces; no tabs.
- Include guards or `#pragma once`.
- One class per header; small functions inline only when obvious.
- Prefer `std::unique_ptr`/`std::shared_ptr` over raw new/delete.

## Testing
- Add/Update tests for new code.
- `./build.sh && ./run_tests.sh` must pass before PR.

## Pull Requests
- Link related Issue(s).
- Describe changes and screenshots if UI.
- Request a review from a teammate. One approval required before merge.
