# Tasks: Modular Dashboard Architecture Refactor

## Task Overview

The component architecture, routing, hooks, and test file are all already in place.
The only remaining work is to fix the failing test suite and verify quality gates pass.

---

- [x] 1. Fix test suite: resolve `React is not defined` error in Vitest
  - Diagnose why the automatic JSX runtime is not being applied during Vitest transforms
  - Fix `vite.config.js` or `setup.js` so `import React` is not required in source files under test
  - Verify all 10 tests in `src/test/DashboardPage.test.jsx` pass
  - Acceptance: `npx vitest run` exits 0 with 10/10 tests passing
  - Files: `frontend/vite.config.js`, `frontend/src/test/setup.js`

- [x] 2. Verify lint passes
  - Run `npx oxlint` on the frontend source
  - Fix any lint errors reported
  - Acceptance: oxlint exits 0 with no errors
  - Files: any files flagged by oxlint

- [x] 3. Confirm no regressions in component structure
  - Verify all required files exist at their expected paths (see design.md file tree)
  - Confirm `HomePage.jsx` does not exist
  - Verify routing: `/` redirects to `/dashboard`, `/dashboard` renders `DashboardPage`, `*` renders `NotFoundPage`
  - Acceptance: file tree matches design.md, no missing files, no extra legacy files
  - Files: `frontend/src/` directory (read-only verification, no changes unless gaps found)
