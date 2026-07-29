/**
 * ValidationErrorTable — re-exports ImportErrorTable under the task-specified name.
 *
 * This thin wrapper keeps the import path `./ValidationErrorTable` stable for
 * ImportPage and tests, while the implementation lives in ImportErrorTable.jsx.
 */
export { default } from './ImportErrorTable'
