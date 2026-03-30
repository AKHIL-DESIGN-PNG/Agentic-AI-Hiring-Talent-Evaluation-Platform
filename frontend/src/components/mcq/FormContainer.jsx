export default function FormContainer({ title, description, children, actions = null }) {
  return (
    <section className="mcq-edit-card">
      {(title || description || actions) && (
        <div className="mcq-edit-card__head">
          <div>
            {title && <h2>{title}</h2>}
            {description && <p>{description}</p>}
          </div>
          {actions}
        </div>
      )}
      {children}
    </section>
  )
}
