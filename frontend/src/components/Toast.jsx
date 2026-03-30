export default function Toast({ open, message }) {
  if (!open || !message) return null
  const display = String(message).split('||')[0]
  return (
    <div className="toast-stack" aria-live="polite">
      <div className="toast-card">{display}</div>
    </div>
  )
}
