import { Link } from 'react-router-dom'

export default function HomePage() {
  return (
    <main className="page container">
      <section className="hero-grid">
        <div>
          <div className="pill">Capstone-ready AI Platform</div>
          <h1>Automate personalized course creation from assessment to certification.</h1>
          <p className="hero-copy">
            This platform helps learners choose a target role, complete an assessment, receive an AI-generated
            course, finish quizzes and assignments, and earn a completion certificate.
          </p>
          <div className="hero-actions">
            <Link to="/register" className="button-primary">Start Free</Link>
            <Link to="/login" className="button-secondary">Login</Link>
          </div>
        </div>
        <div className="card hero-panel">
          <h3>Core workflow</h3>
          <ol className="feature-list">
            <li>Create an account</li>
            <li>Select a target role</li>
            <li>Take an assessment or choose beginner mode</li>
            <li>Generate a personalized course</li>
            <li>Practice in the built-in Python lab with CSV/XLSX files</li>
            <li>Complete quizzes and assignments</li>
            <li>Receive a certificate</li>
          </ol>
        </div>
      </section>

      <section className="three-grid section-gap">
        <div className="card">
          <h3>Assessment-driven</h3>
          <p>Experienced learners can take an assessment and receive topic-focused learning paths.</p>
        </div>
        <div className="card">
          <h3>AI-generated content</h3>
          <p>Modules, lessons, quizzes, assignments, and capstone prompts are generated as structured JSON.</p>
        </div>
        <div className="card">
          <h3>Hands-on practice</h3>
          <p>Includes a built-in Python editor with safe execution and optional CSV/XLSX dataset support for applied learning.</p>
        </div>
      </section>
    </main>
  )
}
