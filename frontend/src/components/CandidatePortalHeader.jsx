export default function CandidatePortalHeader({
  status = 'Pre-Assessment',
  statusTone = 'neutral',
  rightLabel = '',
  candidateName = ''
}) {
  const displayLabel = candidateName || rightLabel

  return (
    <header className="candidate-portal-header">
      <div className="candidate-portal-header__left">
        <span className="candidate-portal-header__brand">AITS Hiring</span>
        <span className="candidate-portal-header__divider" />
        <div className={`candidate-portal-header__status candidate-portal-header__status--${statusTone}`}>
          <span className="candidate-portal-header__status-dot" />
          <span>{status}</span>
        </div>
      </div>
      <div className="candidate-portal-header__right">
        <span>{displayLabel}</span>
      </div>
    </header>
  )
}
