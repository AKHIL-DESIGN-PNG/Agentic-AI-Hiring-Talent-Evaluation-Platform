export default function VerbalTopicCard({ title, description, count, itemLabel, onOpen }) {
  return (
    <article
      className="section-card section-card--interactive"
      onClick={onOpen}
      role="button"
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onOpen()
        }
      }}
    >
      <div className="heading-row">
        <h3 style={{ margin: 0 }}>{title}</h3>
        <span className="status-pill status-pill--completed">
          {count} {itemLabel}
          {count === 1 ? '' : 's'}
        </span>
      </div>
      <p>{description}</p>
    </article>
  )
}
