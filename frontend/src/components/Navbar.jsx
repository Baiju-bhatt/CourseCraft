import { Link, useLocation, useNavigate } from 'react-router-dom'

export default function Navbar() {
  const navigate = useNavigate()
  const location = useLocation()
  const token = localStorage.getItem('token')
  const user = JSON.parse(localStorage.getItem('user') || 'null')
  const isAdmin = Boolean(user?.is_admin)
  const onAdminRoute = location.pathname.startsWith('/admin')

  function logout() {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    navigate(onAdminRoute ? '/admin/login' : '/login')
  }

  return (
    <header className="navbar">
      <div className="container navbar-inner">
        <Link to={isAdmin ? '/admin/portal' : '/'} className="brand">
          <span className="brand-mark">AI</span>
          <span>{isAdmin ? 'Admin Portal' : 'Course Content Generator'}</span>
        </Link>
        <nav className="nav-links">
          {!token ? (
            <>
              <Link to="/">Home</Link>
              <Link to="/login">Login</Link>
              <Link to="/register" className="primary-link">Create Account</Link>
              <Link to="/admin/login" className="button-secondary">Admin</Link>
            </>
          ) : isAdmin ? (
            <>
              <Link to="/admin/portal">Admin Portal</Link>
              <button className="ghost-button" onClick={logout}>Logout</button>
            </>
          ) : (
            <>
              <Link to="/">Home</Link>
              <Link to="/dashboard">Dashboard</Link>
              <Link to="/generate-course">Generate Course</Link>
              <Link to="/practice-lab">Practice Lab</Link>
              <button className="ghost-button" onClick={logout}>Logout</button>
            </>
          )}
        </nav>
      </div>
    </header>
  )
}
