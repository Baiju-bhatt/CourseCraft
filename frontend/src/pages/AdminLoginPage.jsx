import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'

export default function AdminLoginPage() {
  const navigate = useNavigate()
  const [form, setForm] = useState({ email: '', password: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await api.adminLogin(form)
      localStorage.setItem('token', data.token)
      localStorage.setItem('user', JSON.stringify(data.user))
      navigate('/admin/portal')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="page container narrow">
      <div className="card form-card admin-login-card">
        <div className="pill">Admin Workspace</div>
        <h2>Admin Portal Login</h2>
        <p className="subtle">Sign in as an administrator to manage users, courses, assessments, and certificates.</p>
        <form onSubmit={handleSubmit} className="form-grid">
          <label>
            Admin Email
            <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
          </label>
          <label>
            Password
            <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required />
          </label>
          {error && <div className="alert error">{error}</div>}
          <button type="submit" className="button-primary" disabled={loading}>{loading ? 'Signing in...' : 'Open Admin Portal'}</button>
        </form>
        <div className="footer-links subtle footer-note">
          <span>User login? <Link to="/login">Go to learner login</Link></span>
          <span>Default admin can be configured with ADMIN_EMAIL and ADMIN_PASSWORD in backend.</span>
        </div>
      </div>
    </main>
  )
}
