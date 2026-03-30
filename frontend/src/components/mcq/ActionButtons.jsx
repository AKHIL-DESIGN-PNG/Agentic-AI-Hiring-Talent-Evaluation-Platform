export default function ActionButtons({ onSave, onCancel, isSaving }) {
  return (
    <div className="mcq-edit-actions">
      <button className="ghost-btn" type="button" onClick={onCancel}>
        Back
      </button>
      <button className="primary" type="button" onClick={onSave} disabled={isSaving}>
        {isSaving ? 'Saving...' : 'Save'}
      </button>
    </div>
  )
}
