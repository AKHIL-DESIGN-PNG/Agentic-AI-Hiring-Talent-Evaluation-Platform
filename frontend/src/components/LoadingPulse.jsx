export default function LoadingPulse({ fullPage = false }) {
  return (
    <div className={fullPage ? 'loading-pulse-shell loading-pulse-shell--page' : 'loading-pulse-shell'}>
      <div className="pulse" />
    </div>
  )
}

