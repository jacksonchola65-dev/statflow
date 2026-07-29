/**
 * DropZone — re-exports CsvDropZone under the task-specified name.
 *
 * This thin wrapper keeps the import path `./DropZone` stable for
 * ImportPage and tests, while the implementation lives in CsvDropZone.jsx.
 */
export { default } from './CsvDropZone'
