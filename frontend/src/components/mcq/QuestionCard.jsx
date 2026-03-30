import Dropdown from './Dropdown'
import FormContainer from './FormContainer'
import InputField from './InputField'
import OptionEditorCard from './OptionEditorCard'

const difficultyOptions = [
  { value: 'EASY', label: 'EASY' },
  { value: 'MEDIUM', label: 'MEDIUM' },
  { value: 'HARD', label: 'HARD' }
]

export default function QuestionCard({
  question,
  index,
  totalQuestions,
  errors,
  onUpdate,
  onRemove,
  onClearError,
  onMoveQuestion,
  onMoveOption
}) {
  function updateOptionValue(optionId, value) {
    onUpdate({
      ...question,
      options: question.options.map((option) => (
        option.id === optionId ? { ...option, value } : option
      ))
    })
  }

  function addOption() {
    const optionId = `${question.id}-o${Date.now()}`
    onUpdate({
      ...question,
      options: [...question.options, { id: optionId, value: '' }]
    })
  }

  function removeOption(optionId) {
    const nextOptions = question.options.filter((option) => option.id !== optionId)
    const nextCorrectOptionId = question.correctOptionId === optionId ? null : question.correctOptionId
    onUpdate({
      ...question,
      options: nextOptions,
      correctOptionId: nextCorrectOptionId
    })
  }

  return (
    <div
      draggable
      onDragStart={(event) => {
        event.dataTransfer.setData('text/question-id', question.id)
      }}
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        const sourceId = event.dataTransfer.getData('text/question-id')
        if (sourceId && sourceId !== question.id) onMoveQuestion(sourceId, question.id)
      }}
    >
      <FormContainer
      title={`Question ${index + 1}`}
      description={`${question.options.length} option${question.options.length === 1 ? '' : 's'} configured`}
      actions={(
        totalQuestions > 1
          ? <button className="mcq-question-card__remove" type="button" onClick={onRemove}>Delete</button>
          : null
      )}
    >
      <div className="mcq-question-card">
        <InputField
          id={`${question.id}-text`}
          label="Question"
          value={question.text}
          onChange={(value) => {
            onUpdate({ ...question, text: value })
            onClearError('text')
          }}
          placeholder="Enter your question here"
          error={errors?.text}
          multiline
        />

        <Dropdown
          id={`${question.id}-difficulty`}
          label="Difficulty"
          value={question.difficulty}
          onChange={(value) => onUpdate({ ...question, difficulty: value })}
          options={difficultyOptions}
        />

        <div className="mcq-options-section">
          <div className="mcq-options-section__head">
            <div>
              <h3>Options</h3>
              <p>Select the correct answer and edit each option independently.</p>
            </div>
            <button className="ghost-btn" type="button" onClick={addOption}>
              Add Option
            </button>
          </div>

          <div className="mcq-options-section__list">
            {question.options.map((option, optionIndex) => (
                <OptionEditorCard
                  key={option.id}
                  option={option}
                  index={optionIndex}
                  name={`${question.id}-correct-answer`}
                  value={option.value}
                  isCorrect={question.correctOptionId === option.id}
                  error={errors?.options?.[option.id]}
                  canRemove={question.options.length > 4}
                  onChange={(value) => {
                    updateOptionValue(option.id, value)
                    onClearError('option', option.id)
                  }}
                  onSelectCorrect={() => {
                    onUpdate({ ...question, correctOptionId: option.id })
                    onClearError('correctAnswer')
                  }}
                  onRemove={removeOption}
                  onMoveOption={(sourceId, targetId) => onMoveOption(question.id, sourceId, targetId)}
                />
            ))}
          </div>

          {errors?.correctAnswer && (
            <p className="mcq-options-section__error">{errors.correctAnswer}</p>
          )}
        </div>
      </div>
      </FormContainer>
    </div>
  )
}
