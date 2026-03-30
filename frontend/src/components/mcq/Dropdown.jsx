export default function Dropdown({ id, label, value, options, onChange, error = '' }) {
  return (
    <label className="mcq-edit-field" htmlFor={id}>
      <span className="mcq-edit-field__label">{label}</span>
      <select
        id={id}
        className={`mcq-edit-input mcq-edit-input--select${error ? ' mcq-edit-input--error' : ''}`}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {error && <span className="mcq-edit-field__error">{error}</span>}
    </label>
  )
}
