import LoadingPulse from './LoadingPulse'

export default function LoadingOverlay({ open = false, label = 'Loading...' }) {
  if (!open) return null

  return (
    <div className="loading-overlay" aria-live="polite" aria-busy="true">
      <div className="loading-overlay__content">
        <LoadingPulse />
        <span>{label}</span>
      </div>
    </div>
  )
}
