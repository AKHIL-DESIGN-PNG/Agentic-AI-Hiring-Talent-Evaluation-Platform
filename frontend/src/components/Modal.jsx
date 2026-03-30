export default function Modal({
  open,
  title,
  onClose,
  children,
  disableBackdropClose = false,
  hideCloseButton = false,
  hideHeader = false,
  className = ''
}) {
  if (!open) return null

  function handleBackdrop() {
    if (!disableBackdropClose && typeof onClose === 'function') {
      onClose()
    }
  }

  return (
    <div className="modal-backdrop" onClick={handleBackdrop}>
      <div className={`modal ${className}`.trim()} onClick={(event) => event.stopPropagation()}>
        {!hideHeader && (
          <div className="modal-head">
            <h3>{title}</h3>
            {!hideCloseButton && (
              <button onClick={onClose} className="icon-btn" type="button">
                x
              </button>
            )}
          </div>
        )}
        {children}
      </div>
    </div>
  )
}

