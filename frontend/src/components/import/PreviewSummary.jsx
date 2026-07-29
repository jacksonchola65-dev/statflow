/**
 * PreviewSummary — re-exports ImportSummary under the task-specified name.
 *
 * This thin wrapper keeps the import path `./PreviewSummary` stable for
 * ImportPage and tests, while the implementation lives in ImportSummary.jsx.
 */
export { default } from './ImportSummary'
