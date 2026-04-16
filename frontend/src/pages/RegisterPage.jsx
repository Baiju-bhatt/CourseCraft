import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'

export default function RegisterPage() {
  const navigate = useNavigate()
  const [form, setForm] = useState({
    full_name: '',
    email: '',
    password: '',
    current_role: '',
    experience_level: 'Beginner',
  })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await api.register(form)
      localStorage.setItem('token', data.token)
      localStorage.setItem('user', JSON.stringify(data.user))
      navigate('/dashboard')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="page container narrow">
      <div className="card form-card">
        <h2>Create Account</h2>
        <p className="subtle">Build your profile and start generating custom learning paths.</p>
        <form onSubmit={handleSubmit} className="form-grid two-column">
          <label>
            Full Name
            <input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} required />
          </label>
          <label>
            Email
            <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
          </label>
          <label>
            Password
            <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required />
          </label>
          <label>
            Current Role
            <input value={form.current_role} onChange={(e) => setForm({ ...form, current_role: e.target.value })} placeholder="Optional" />
          </label>
          <label className="full-span">
            Current Experience Level
            <select value={form.experience_level} onChange={(e) => setForm({ ...form, experience_level: e.target.value })}>
              <option>Beginner</option>
              <option>Intermediate</option>
              <option>Experienced</option>
            </select>
          </label>
          {error && <div className="alert error full-span">{error}</div>}
          <button type="submit" className="button-primary full-span" disabled={loading}>{loading ? 'Creating account...' : 'Create Account'}</button>
        </form>
        <p className="subtle footer-note">Already have an account? <Link to="/login">Login</Link></p>
      </div>
    </main>
  )
}
