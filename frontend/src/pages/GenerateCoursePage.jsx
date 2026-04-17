import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'

export default function GenerateCoursePage() {
  const navigate = useNavigate()
  const [step, setStep] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [questions, setQuestions] = useState([])
  const [assessmentResult, setAssessmentResult] = useState(null)
  const [answers, setAnswers] = useState([])
  const [config, setConfig] = useState({ llm_enabled: false, model: null, suggested_roles: [] })
  const isGenerating = loading && (step === 1 || step === 3)
  const [form, setForm] = useState({
    target_role: '',
    current_role: '',
    experience_type: 'beginner',
  })

  useEffect(() => {
    api.getConfig()
      .then((data) => setConfig(data))
      .catch(() => undefined)
  }, [])

  const trimmedRole = useMemo(() => form.target_role.trim(), [form.target_role])

  function updateForm(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }))
  }

  async function handleStartAssessment() {
    if (!trimmedRole) {
      setError('Please enter a target role.')
      return
    }

    setError('')
    setLoading(true)
    try {
      const data = await api.getAssessmentQuestions({ target_role: trimmedRole })
      setQuestions(data.questions)
      setAnswers(data.questions.map((question) => ({ question_id: question.id, selected_option_index: null })))
      setStep(2)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function submitAssessment() {
    if (answers.some((answer) => answer.selected_option_index === null)) {
      setError('Please answer all questions before submitting the assessment.')
      return
    }

    setError('')
    setLoading(true)
    try {
      const result = await api.evaluateAssessment({ target_role: trimmedRole, questions, answers })
      setAssessmentResult(result)
      setStep(3)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function generateCourse() {
    if (!trimmedRole) {
      setError('Please enter a target role.')
      return
    }

    setError('')
    setLoading(true)
    try {
      const data = await api.generateCourse({ ...form, target_role: trimmedRole, assessment_result: assessmentResult })
      navigate(`/course/${data.course_id}`)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function generateWithoutAssessment() {
    if (!trimmedRole) {
      setError('Please enter a target role.')
      return
    }

    setError('')
    setLoading(true)
    try {
      const data = await api.generateCourse({ ...form, target_role: trimmedRole, assessment_result: null })
      navigate(`/course/${data.course_id}`)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  function updateAnswer(index, optionIndex) {
    setAnswers((previous) => previous.map((answer, answerIndex) => {
      if (answerIndex !== index) return answer
      return { ...answer, selected_option_index: optionIndex }
    }))
  }

  return (
    <main className="page container narrow-wide">
      <div className="card form-card">
        {isGenerating && (
          <div className="loading-overlay" role="status" aria-live="polite">
            <div className="loading-overlay-card">
              <div className="loading-spinner" />
              <h3>{step === 3 ? 'Generating your personalized course...' : 'Working on your request...'}</h3>
              <p className="subtle">This can take a little time because the platform is building role-specific modules, quizzes, and practice tasks.</p>
            </div>
          </div>
        )}
        <div className="page-heading-row">
          <div>
            <h2>Generate Personalized Course</h2>
            <p className="subtle">
              Enter a target role manually and generate either a beginner crash course or an assessment-based personalized path.
            </p>
          </div>
          <div className={`engine-badge ${config.llm_enabled ? 'ready' : 'fallback'}`}>
            <span className="engine-dot" />
            <div>
              <strong>{config.llm_enabled ? 'LLM Enabled' : 'Fallback Mode'}</strong>
              <small>{config.llm_enabled ? config.model : 'Add a Hugging Face token to enable live generation.'}</small>
            </div>
          </div>
        </div>

        {step === 1 && (
          <div className="form-grid">
            <label>
              Target Role
              <input
                value={form.target_role}
                onChange={(e) => updateForm('target_role', e.target.value)}
                placeholder="Example: Data Engineer, Data Scientist, AI Developer, ML Engineer"
              />
            </label>

            <label>
              Current Role
              <input
                value={form.current_role}
                onChange={(e) => updateForm('current_role', e.target.value)}
                placeholder="Example: Software Developer"
              />
            </label>

            <label>
              Learning Path
              <select value={form.experience_type} onChange={(e) => updateForm('experience_type', e.target.value)}>
                <option value="beginner">Beginner / Career Switch</option>
                <option value="experienced">Experienced / Assessment-Based</option>
              </select>
            </label>

            <div className="card note-card">
              <p className="muted-label">How this works</p>
              <ul className="compact-list">
                <li>Type a target role manually. This version is optimized for Python-related roles such as Data Engineer, Data Scientist, AI Developer, and ML Engineer.</li>
                <li>The final course plan focuses more on weak topics when an assessment is used.</li>
                <li>The platform keeps the course flow, capstone, and supporting features aligned around the role you enter.</li>
              </ul>
            </div>

            {error && <div className="alert error">{error}</div>}

            {form.experience_type === 'experienced' ? (
              <button className="button-primary" onClick={handleStartAssessment} disabled={loading}>
                {loading ? 'Preparing assessment...' : 'Start Assessment'}
              </button>
            ) : (
              <button className="button-primary" onClick={generateWithoutAssessment} disabled={loading}>
                {loading ? 'Generating course...' : 'Generate Beginner Course'}
              </button>
            )}
          </div>
        )}

        {step === 2 && (
          <div>
            <div className="assessment-header">
              <div>
                <h3>{trimmedRole} Assessment</h3>
                <p className="subtle">Answer all questions. Your weak areas will be emphasized in the generated course.</p>
              </div>
              <button className="ghost-button" onClick={() => setStep(1)} disabled={loading}>Back</button>
            </div>

            <div className="assessment-list">
              {questions.map((question, index) => (
                <div key={question.id} className="assessment-card">
                  <div className="question-meta-row"><p className="muted-label">{question.topic}</p><span className={`difficulty-badge ${String(question.difficulty || 'Medium').toLowerCase()}`}>{question.difficulty || 'Medium'}</span></div>
                  <h4>{index + 1}. {question.question}</h4>
                  <div className="option-list">
                    {question.options.map((option, optionIndex) => {
                      const inputId = `question-${question.id}-option-${optionIndex}`
                      return (
                        <label key={inputId} htmlFor={inputId} className="option-item">
                          <input
                            id={inputId}
                            type="radio"
                            name={`question-${question.id}`}
                            checked={answers[index]?.selected_option_index === optionIndex}
                            onChange={() => updateAnswer(index, optionIndex)}
                          />
                          <span className="option-text">{option}</span>
                        </label>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
            {error && <div className="alert error">{error}</div>}
            <div className="form-actions-left">
              <button className="button-primary" onClick={submitAssessment} disabled={loading}>
                {loading ? 'Evaluating...' : 'Submit Assessment'}
              </button>
            </div>
          </div>
        )}

        {step === 3 && assessmentResult && (
          <div>
            <div className="assessment-header">
              <div>
                <h3>Assessment Result</h3>
                <p className="subtle">The course below will prioritize the topics where you need the most improvement.</p>
              </div>
              <button className="ghost-button" onClick={() => setStep(2)} disabled={loading}>Review Answers</button>
            </div>
            <div className="three-grid section-gap">
              <div className="card"><p className="muted-label">Score</p><h3>{assessmentResult.score}%</h3></div>
              <div className="card"><p className="muted-label">Strengths</p><p>{assessmentResult.strengths.join(', ')}</p></div>
              <div className="card"><p className="muted-label">Weaknesses</p><p>{assessmentResult.weaknesses.join(', ')}</p></div>
            </div>
            <p className="subtle">Recommendation: {assessmentResult.recommendation}</p>
            {error && <div className="alert error">{error}</div>}
            <div className="form-actions-left">
              <button className="button-primary" onClick={generateCourse} disabled={loading}>
                {loading ? 'Generating personalized course...' : 'Generate Personalized Course'}
              </button>
            </div>
          </div>
        )}
      </div>
    </main>
  )
}
