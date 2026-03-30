export default function InputField({
  id,
  label,
  value,
  onChange,
  placeholder = '',
  error = '',
  multiline = false
}) {
  return (
    <label className="mcq-edit-field" htmlFor={id}>
      <span className="mcq-edit-field__label">{label}</span>
      {multiline ? (
        <textarea
          id={id}
          className={`mcq-edit-input mcq-edit-input--textarea${error ? ' mcq-edit-input--error' : ''}`}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
        />
      ) : (
        <input
          id={id}
          className={`mcq-edit-input${error ? ' mcq-edit-input--error' : ''}`}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
        />
      )}
      {error && <span className="mcq-edit-field__error">{error}</span>}
    </label>
  )
}
