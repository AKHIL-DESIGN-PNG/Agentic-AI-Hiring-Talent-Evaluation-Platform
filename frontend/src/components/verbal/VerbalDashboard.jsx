import Modal from '../Modal'
import TopNav from '../TopNav'
import ActionButtons from '../mcq/ActionButtons'

export function VerbalDashboardShell({
  title,
  countText,
  error,
  saving,
  onBack,
  onSave,
  children
}) {
  return (
    <div className="mcq-edit-page-shell verbal-dashboard-shell">
      <TopNav />
      <main className="mcq-edit-page verbal-dashboard-page">
        <header className="mcq-edit-header verbal-dashboard-header">
          <div className="verbal-dashboard-header__copy">
            <p className="muted">AITS &gt; Assessments &gt; Verbal Editor</p>
            <div className="verbal-dashboard-header__title-row">
              <h1>{title}</h1>
              <span className="status-pill status-pill--completed">{countText}</span>
            </div>
          </div>
          <div className="verbal-dashboard-header__actions">
            <ActionButtons onCancel={onBack} onSave={onSave} isSaving={saving} />
          </div>
        </header>
        {error && <p className="error">{error}</p>}
        {children}
      </main>
    </div>
  )
}

export function VerbalDashboardEmpty({
  title,
  description,
  actionLabel,
  onAction,
  secondaryActionLabel,
  onSecondaryAction
}) {
  return (
    <section className="mcq-edit-card verbal-dashboard-empty">
      <p className="eyebrow">{title}</p>
      <h2>No items yet</h2>
      <p>{description}</p>
      <div className="actions-row actions-row--center">
        {secondaryActionLabel && onSecondaryAction ? (
          <button className="ghost-btn" type="button" onClick={onSecondaryAction}>
            {secondaryActionLabel}
          </button>
        ) : null}
        <button className="primary" type="button" onClick={onAction}>
          {actionLabel}
        </button>
      </div>
    </section>
  )
}

export function VerbalDashboardCard({
  index,
  title,
  subtitle,
  details = [],
  extraActions = null,
  onEdit,
  onDelete
}) {
  return (
    <article className="verbal-dashboard-card">
      <div className="verbal-dashboard-card__header">
        <div className="verbal-dashboard-card__title-wrap">
          <span className="verbal-dashboard-card__index">{index}</span>
          <div>
            <h3>{title}</h3>
            {subtitle ? <p>{subtitle}</p> : null}
          </div>
        </div>
        <div className="verbal-dashboard-card__actions">
          {extraActions}
          <button className="ghost-btn" type="button" onClick={onEdit}>
            Edit
          </button>
          <button className="ghost-btn verbal-dashboard-card__delete" type="button" onClick={onDelete}>
            Delete
          </button>
        </div>
      </div>
      <div className="verbal-dashboard-card__details">
        {details.filter(Boolean).map((detail) => (
          <div key={detail.label} className="verbal-dashboard-card__detail">
            <span>{detail.label}</span>
            <strong>{detail.value}</strong>
          </div>
        ))}
      </div>
    </article>
  )
}

export function VerbalEditorModal({ open, title, onClose, onSubmit, submitLabel, children }) {
  return (
    <Modal open={open} title={title} onClose={onClose}>
      <div className="modal-body verbal-dashboard-modal__body">
        {children}
        <div className="actions-row">
          <button className="ghost-btn" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="primary" type="button" onClick={onSubmit}>
            {submitLabel}
          </button>
        </div>
      </div>
    </Modal>
  )
}

export function VerbalDeleteModal({ open, title, onClose, onConfirm }) {
  return (
    <Modal open={open} title="Delete item" onClose={onClose}>
      <div className="modal-body verbal-dashboard-modal__body">
        <p>
          Delete <strong>{title}</strong>? This cannot be undone.
        </p>
        <div className="actions-row">
          <button className="ghost-btn" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="primary verbal-dashboard-delete-btn" type="button" onClick={onConfirm}>
            Delete
          </button>
        </div>
      </div>
    </Modal>
  )
}
