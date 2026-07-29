/**
 * SelectField — accessible labelled select with a custom chevron icon.
 *
 * Visual changes from previous version:
 *  - Minimum height 40 px (h-10) — aligns to 8 px spacing grid
 *  - appearance-none removes the native OS chevron
 *  - Custom chevron SVG (aria-hidden) absolutely positioned at right edge
 *  - Border uses design token --sf-border-input
 *  - Surface uses slate-800/80 to match card surfaces
 *  - focus-visible ring uses --sf-focus-ring with ring-offset so it
 *    reads clearly against dark backgrounds
 *  - disabled opacity reduced to 40 % (more refined than 50 %)
 *  - Hover border brightens subtly
 *
 * All prop names, semantics, and callback signatures are unchanged.
 *
 * @param {{
 *   label:    string,
 *   value:    string | number,
 *   onChange: (value: string) => void,
 *   disabled?: boolean,
 *   children: import('react').ReactNode,
 * }} props
 */
export default function SelectField({ label, value, onChange, disabled = false, children }) {
  const id = label.toLowerCase().replace(/\s+/g, '-')

  return (
    <div className="flex flex-col gap-1.5">
      {/* Label — H3-style typography from design tokens */}
      <label
        htmlFor={id}
        className="
          text-[11px] font-medium uppercase
          tracking-[var(--sf-tracking-widest)]
          text-[var(--sf-text-subtle)]
        "
      >
        {label}
      </label>

      {/* Wrapper provides positioning context for the chevron icon */}
      <div className="relative">
        <select
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          className="
            w-full h-10
            appearance-none
            rounded-lg
            border border-[var(--sf-border-input)]
            bg-slate-800/80
            pl-3 pr-9 py-0
            text-sm text-white
            transition-colors duration-150
            hover:border-[var(--sf-border-hover)]
            focus-visible:outline-none
            focus-visible:ring-2
            focus-visible:ring-[var(--sf-focus-ring)]
            focus-visible:ring-offset-2
            focus-visible:ring-offset-[var(--sf-bg)]
            disabled:opacity-40
            disabled:cursor-not-allowed
            disabled:hover:border-[var(--sf-border-input)]
          "
        >
          {children}
        </select>

        {/* Custom chevron — decorative, not interactive */}
        <svg
          aria-hidden="true"
          focusable="false"
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 20 20"
          fill="currentColor"
          className="
            pointer-events-none
            absolute right-3 top-1/2 -translate-y-1/2
            w-4 h-4
            text-[var(--sf-text-subtle)]
          "
        >
          <path
            fillRule="evenodd"
            d="M5.22 8.22a.75.75 0 0 1 1.06 0L10 11.94l3.72-3.72a.75.75 0 1 1 1.06 1.06l-4.25 4.25a.75.75 0 0 1-1.06 0L5.22 9.28a.75.75 0 0 1 0-1.06z"
            clipRule="evenodd"
          />
        </svg>
      </div>
    </div>
  )
}
