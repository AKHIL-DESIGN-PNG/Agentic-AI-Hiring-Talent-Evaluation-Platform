export default function OptionEditorCard({
  option,
  index,
  name,
  value,
  isCorrect,
  error,
  canRemove,
  onChange,
  onSelectCorrect,
  onRemove,
  onMoveOption
}) {
  const optionLabel = String.fromCharCode(65 + index)

  return (
    <div className={`mcq-option-card${isCorrect ? ' mcq-option-card--selected' : ''}`}>
      <div
        className="mcq-option-card__marker"
        aria-hidden="true"
        draggable
        onDragStart={(event) => {
          event.dataTransfer.setData('text/option-id', option.id)
        }}
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          const sourceId = event.dataTransfer.getData('text/option-id')
          if (sourceId && sourceId !== option.id) onMoveOption(sourceId, option.id)
        }}
      >
        ::
      </div>
      <label className="mcq-option-card__radio">
        <input
          type="radio"
          name={name}
          checked={isCorrect}
          onChange={onSelectCorrect}
        />
        <span>{optionLabel}</span>
      </label>
      <div className="mcq-option-card__body">
        <input
          className={`mcq-edit-input${error ? ' mcq-edit-input--error' : ''}`}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={`Option ${optionLabel}`}
        />
        {error && <span className="mcq-edit-field__error">{error}</span>}
      </div>
      {canRemove && (
        <button className="mcq-option-card__remove" type="button" onClick={() => onRemove(option.id)}>
          Remove
        </button>
      )}
    </div>
  )
}
