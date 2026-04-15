import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import StatCard from '../components/StatCard'

export default function DashboardPage() {
  const [summary, setSummary] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.getDashboard()
      .then(setSummary)
      .catch((err) => setError(err.message))
  }, [])

  if (error) {
    return <main className="page container"><div className="alert error">{error}</div></main>
  }

  if (!summary) {
    return <main className="page container"><div className="card">Loading dashboard...</div></main>
  }

  return (
    <main className="page container">
      <section className="dashboard-header">
        <div>
          <h1>Welcome, {summary.user_name}</h1>
          <p className="subtle">Review your progress and continue building AI-generated course experiences.</p>
        </div>
        <div className="hero-actions">
          <Link to="/generate-course" className="button-primary">Generate New Course</Link>
          <Link to="/practice-lab" className="button-secondary">Open Practice Lab</Link>
        </div>
      </section>

      <section className="three-grid section-gap">
        <StatCard label="Total Courses" value={summary.stats.total_courses} />
        <StatCard label="Completed Courses" value={summary.stats.completed_courses} />
        <StatCard label="Assessments Taken" value={summary.stats.total_assessments} />
      </section>


      <section className="section-gap">
        <div className="card">
          <div className="admin-card-header">
            <div>
              <h3>Hands-on coding practice</h3>
              <p className="subtle">Use the Practice Lab to write Python, upload CSV/XLSX datasets, and test your code safely inside the application.</p>
            </div>
            <Link to="/practice-lab" className="button-secondary">Go to Lab</Link>
          </div>
        </div>
      </section>

      <section className="section-gap">
        <div className="card">
          <h3>Recent Courses</h3>
          {summary.recent_courses.length === 0 ? (
            <p className="subtle">No courses yet. Generate your first course.</p>
          ) : (
            <div className="table-like">
              {summary.recent_courses.map((course) => (
                <Link key={course.course_id} to={`/course/${course.course_id}`} className="table-row">
                  <span>{course.title}</span>
                  <span>{course.target_role}</span>
                  <span className={`status-chip ${course.status}`}>{course.status}</span>
                </Link>
              ))}
            </div>
          )}
        </div>
      </section>
    </main>
  )
}
