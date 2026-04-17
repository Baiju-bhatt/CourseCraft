import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, notifyAuthChanged } from '../api'

export default function LoginPage() {
  const navigate = useNavigate()
  const [form, setForm] = useState({ email: '', password: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await api.login(form)
      localStorage.setItem('token', data.token)
      localStorage.setItem('user', JSON.stringify(data.user))
      notifyAuthChanged()
      navigate(data.user?.is_admin ? '/admin/portal' : '/dashboard')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="page container narrow">
      <div className="card form-card">
        <h2>Login</h2>
        <p className="subtle">Access your dashboard and generate personalized course content.</p>
        <form onSubmit={handleSubmit} className="form-grid">
          <label>
            Email
            <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
          </label>
          <label>
            Password
            <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required />
          </label>
          {error && <div className="alert error">{error}</div>}
          <button type="submit" className="button-primary" disabled={loading}>{loading ? 'Signing in...' : 'Login'}</button>
        </form>
        <div className="footer-links subtle footer-note">
          <span>No account yet? <Link to="/register">Create one</Link></span>
          <span>Admin access? <Link to="/admin/login">Open admin portal</Link></span>
        </div>
      </div>
    </main>
  )
}
