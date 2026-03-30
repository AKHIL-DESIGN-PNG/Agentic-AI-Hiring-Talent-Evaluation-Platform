import { useState, useRef, useEffect } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import Modal from './Modal'

function BrandLogo() {
  return (
    <div className="brand-logo">
      <span>A</span>
    </div>
  )
}

function readAdminProfile() {
  try {
    return JSON.parse(localStorage.getItem('admin_profile') || sessionStorage.getItem('admin_profile') || '{}')
  } catch {
    return {}
  }
}

export default function TopNav() {
  const navigate = useNavigate()
  const location = useLocation()

  const [modalType, setModalType] = useState('')
  const [openProfile, setOpenProfile] = useState(false)

  const [profile, setProfile] = useState(readAdminProfile())

  const [editField, setEditField] = useState(null)
  const [nameInput, setNameInput] = useState(profile.full_name || '')
  const [companyInput, setCompanyInput] = useState(profile.company_name || '')

  const profileRef = useRef(null)

  const adminName = profile.full_name || profile.name || 'Admin User'
  const adminEmail = profile.email || 'admin@aitshackminds.com'
  const companyName = profile.company_name || 'Your Company'

  function persistProfile(updated) {
    localStorage.setItem('admin_profile', JSON.stringify(updated))
    sessionStorage.setItem('admin_profile', JSON.stringify(updated))
    setProfile(updated)
  }

  function logout() {
    localStorage.removeItem('admin_token')
    localStorage.removeItem('admin_profile')
    sessionStorage.removeItem('admin_token')
    sessionStorage.removeItem('admin_profile')
    navigate('/admin/auth')
  }

  useEffect(() => {
    function handleClickOutside(event) {
      if (profileRef.current && !profileRef.current.contains(event.target)) {
        setOpenProfile(false)
        setEditField(null)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  function saveName() {
    if (!nameInput.trim()) return

    const updated = { ...profile, full_name: nameInput }
    persistProfile(updated)
    setEditField(null)
  }

  function saveCompany() {
    if (!companyInput.trim()) return

    const updated = { ...profile, company_name: companyInput }
    persistProfile(updated)
    setEditField(null)
  }

  const EditIcon = ({ onClick }) => (
    <button className="edit-btn-inline" type="button" onClick={onClick}>
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
      >
        <path d="M12 20h9" />
        <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z" />
      </svg>
    </button>
  )

  return (
    <>
      <header className="top-nav">
        <Link className="brand brand-link" to="/admin/assessments">
          <BrandLogo />
          <div className="brand-copy">
            <span className="brand-copy__name">AITS HACKMINDS</span>
            <span className="brand-copy__tag">Smart hiring assessments</span>
          </div>
        </Link>

        <nav className="top-nav__menu">
          <Link
            className={
              !modalType && location.pathname.startsWith('/admin/assessments')
                ? 'nav-pill active'
                : 'nav-pill'
            }
            to="/admin/assessments"
          >
            Assessments
          </Link>

          <button
            className={modalType === 'about' ? 'nav-pill active' : 'nav-pill'}
            type="button"
            onClick={() => setModalType('about')}
          >
            About
          </button>

          <button
            className={modalType === 'contact' ? 'nav-pill active' : 'nav-pill'}
            type="button"
            onClick={() => setModalType('contact')}
          >
            Contact
          </button>
        </nav>

        <div className="top-nav__actions">
          <div className="profile-wrapper" ref={profileRef}>
            <div className="avatar" onClick={() => setOpenProfile(!openProfile)}>
              {adminName.charAt(0).toUpperCase()}
            </div>

            {openProfile && (
              <div className="profile-dropdown">
                <div className="profile-header">
                  <div className="avatar large">
                    {adminName.charAt(0).toUpperCase()}
                  </div>

                  <div className="profile-text">
                    <strong>{adminName}</strong>
                    <span>{adminEmail}</span>
                  </div>
                </div>

                <div className="divider" />

                <div className="profile-row">
                  {editField === 'name' ? (
                    <>
                      <input
                        value={nameInput}
                        onChange={(event) => setNameInput(event.target.value)}
                      />
                      <div className="inline-actions">
                        <button type="button" onClick={saveName}>✓</button>
                        <button type="button" onClick={() => setEditField(null)}>✕</button>
                      </div>
                    </>
                  ) : (
                    <>
                      <p><b>Name:</b> {adminName}</p>
                      <EditIcon onClick={() => setEditField('name')} />
                    </>
                  )}
                </div>

                <p><b>Email:</b> {adminEmail}</p>

                <div className="profile-row">
                  {editField === 'company' ? (
                    <>
                      <input
                        value={companyInput}
                        onChange={(event) => setCompanyInput(event.target.value)}
                      />
                      <div className="inline-actions">
                        <button type="button" onClick={saveCompany}>✓</button>
                        <button type="button" onClick={() => setEditField(null)}>✕</button>
                      </div>
                    </>
                  ) : (
                    <>
                      <p><b>Company:</b> {companyName}</p>
                      <EditIcon onClick={() => setEditField('company')} />
                    </>
                  )}
                </div>

                <div className="divider" />

                <button className="logout-btn" type="button" onClick={logout}>
                  Logout
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      <Modal open={modalType === 'about'} onClose={() => setModalType('')}>
        <div className="modal-content-modern">
          <div className="about-box">
            <h3>About AITS HackMinds</h3>

            <p className="about-desc">
              AITS HackMinds is a smart hiring platform designed to simplify candidate evaluation using structured assessments and AI-driven insights.
            </p>

            <div className="about-features">
              <div className="about-item">
                <span>⚡</span>
                <p>Create and manage assessments easily</p>
              </div>

              <div className="about-item">
                <span>📊</span>
                <p>Analyze candidate performance with insights</p>
              </div>

              <div className="about-item">
                <span>🤖</span>
                <p>AI-powered evaluation and recommendations</p>
              </div>
            </div>

            <button className="primary modal-btn" type="button" onClick={() => setModalType('')}>
              Got it
            </button>
          </div>
        </div>
      </Modal>

      <Modal open={modalType === 'contact'} onClose={() => setModalType('')}>
        <div className="modal-content-modern">
          <div className="modal-header">
            <h3>Contact Us</h3>
          </div>

          <div className="contact-info">
            <div className="contact-item">
              <div className="contact-icon">📧</div>
              <div>
                <span className="contact-label">Email</span>
                <p className="contact-value">support@aitshackminds.com</p>
              </div>
            </div>

            <div className="contact-item">
              <div className="contact-icon">📞</div>
              <div>
                <span className="contact-label">Phone</span>
                <p className="contact-value">+91 98765 43210</p>
              </div>
            </div>
          </div>

          <button className="primary modal-btn" type="button" onClick={() => setModalType('')}>
            Got it
          </button>
        </div>
      </Modal>
    </>
  )
}
