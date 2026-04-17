import { useEffect, useState } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import Navbar from './components/Navbar'
import HomePage from './pages/HomePage'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import DashboardPage from './pages/DashboardPage'
import GenerateCoursePage from './pages/GenerateCoursePage'
import CoursePage from './pages/CoursePage'
import PracticeLabPage from './pages/PracticeLabPage'
import AdminLoginPage from './pages/AdminLoginPage'
import AdminPortalPage from './pages/AdminPortalPage'
import ChatbotWidget from './components/ChatbotWidget'

function getAuthSnapshot() {
  const token = localStorage.getItem('token')
  const user = JSON.parse(localStorage.getItem('user') || 'null')
  return { token, user }
}

function PrivateRoute({ children }) {
  const token = localStorage.getItem('token')
  return token ? children : <Navigate to="/login" replace />
}

function AdminRoute({ children }) {
  const token = localStorage.getItem('token')
  const user = JSON.parse(localStorage.getItem('user') || 'null')
  if (!token) {
    return <Navigate to="/admin/login" replace />
  }
  if (!user?.is_admin) {
    return <Navigate to="/dashboard" replace />
  }
  return children
}

export default function App() {
  const location = useLocation()
  const [auth, setAuth] = useState(getAuthSnapshot())

  useEffect(() => {
    const syncAuth = () => setAuth(getAuthSnapshot())
    window.addEventListener('storage', syncAuth)
    window.addEventListener('auth-change', syncAuth)
    return () => {
      window.removeEventListener('storage', syncAuth)
      window.removeEventListener('auth-change', syncAuth)
    }
  }, [])

  return (
    <div className="app-shell">
      <Navbar />
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/admin/login" element={<AdminLoginPage />} />
        <Route
          path="/admin/portal"
          element={
            <AdminRoute>
              <AdminPortalPage />
            </AdminRoute>
          }
        />
        <Route
          path="/dashboard"
          element={
            <PrivateRoute>
              <DashboardPage />
            </PrivateRoute>
          }
        />
        <Route
          path="/generate-course"
          element={
            <PrivateRoute>
              <GenerateCoursePage />
            </PrivateRoute>
          }
        />
        <Route
          path="/practice-lab"
          element={
            <PrivateRoute>
              <PracticeLabPage />
            </PrivateRoute>
          }
        />
        <Route
          path="/course/:courseId"
          element={
            <PrivateRoute>
              <CoursePage />
            </PrivateRoute>
          }
        />
      </Routes>
      {auth.token && !auth.user?.is_admin ? <ChatbotWidget /> : null}
    </div>
  )
}
