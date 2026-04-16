import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api'

function getProgressKey(courseId) {
  return `course-progress-${courseId}`
}

export default function CoursePage() {
  const { courseId } = useParams()
  const [data, setData] = useState(null)
  const [certificate, setCertificate] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [expandedModules, setExpandedModules] = useState({})
  const [activeModuleIndex, setActiveModuleIndex] = useState(0)
  const [activeLessonIndex, setActiveLessonIndex] = useState(0)
  const [lessonNotes, setLessonNotes] = useState({})
  const [completedLessons, setCompletedLessons] = useState({})
  const [quizAnswers, setQuizAnswers] = useState({})
  const [quizResults, setQuizResults] = useState({})

  useEffect(() => {
    api.getCourse(courseId)
      .then((response) => {
        setData(response)
        const initialExpanded = {}
        response.course.modules.forEach((module, index) => {
          initialExpanded[index] = index === 0
        })
        setExpandedModules(initialExpanded)

        const saved = localStorage.getItem(getProgressKey(courseId))
        if (saved) {
          const parsed = JSON.parse(saved)
          setLessonNotes(parsed.lessonNotes || {})
          setCompletedLessons(parsed.completedLessons || {})
          setQuizAnswers(parsed.quizAnswers || {})
          setQuizResults(parsed.quizResults || {})
        }
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [courseId])

  useEffect(() => {
    localStorage.setItem(getProgressKey(courseId), JSON.stringify({
      lessonNotes,
      completedLessons,
      quizAnswers,
      quizResults,
    }))
  }, [courseId, lessonNotes, completedLessons, quizAnswers, quizResults])

  const course = data?.course
  const activeModule = course?.modules?.[activeModuleIndex]
  const activeLesson = activeModule?.lessons?.[activeLessonIndex]

  function lessonKey(moduleIndex, lessonIndex) {
    return `${moduleIndex}-${lessonIndex}`
  }

  const totalLessons = useMemo(() => (
    course?.modules?.reduce((total, module) => total + (module.lessons?.length || 0), 0) || 0
  ), [course])

  const totalQuizUnits = course?.modules?.length || 0
  const totalTrackUnits = totalLessons + totalQuizUnits

  const completedCount = useMemo(() => Object.values(completedLessons).filter(Boolean).length, [completedLessons])
  const submittedQuizCount = useMemo(() => Object.values(quizResults).filter((result) => result?.submitted).length, [quizResults])
  const progressPercent = totalTrackUnits ? Math.round(((completedCount + submittedQuizCount) / totalTrackUnits) * 100) : 0

  const moduleProgress = useMemo(() => {
    if (!course?.modules) {
      return []
    }
    return course.modules.map((module, moduleIndex) => {
      const lessonTotal = module.lessons?.length || 0
      const lessonCompleted = module.lessons.reduce((count, _lesson, lessonIndex) => {
        return count + (completedLessons[lessonKey(moduleIndex, lessonIndex)] ? 1 : 0)
      }, 0)
      const quizDone = quizResults[String(moduleIndex)]?.submitted ? 1 : 0
      const totalItems = lessonTotal + 1
      const completedItems = lessonCompleted + quizDone
      const percent = totalItems ? Math.round((completedItems / totalItems) * 100) : 0
      return {
        lessonCompleted,
        lessonTotal,
        quizDone: Boolean(quizDone),
        totalItems,
        completedItems,
        percent,
      }
    })
  }, [course, completedLessons, quizResults])

  const completedModuleCount = moduleProgress.filter((item) => item.percent === 100).length

  function selectLesson(moduleIndex, lessonIndex) {
    setActiveModuleIndex(moduleIndex)
    setActiveLessonIndex(lessonIndex)
    setExpandedModules((prev) => ({ ...prev, [moduleIndex]: true }))
  }

  function toggleModule(moduleIndex) {
    setExpandedModules((prev) => ({ ...prev, [moduleIndex]: !prev[moduleIndex] }))
  }

  function handleNoteChange(value) {
    const key = lessonKey(activeModuleIndex, activeLessonIndex)
    setLessonNotes((prev) => ({ ...prev, [key]: value }))
  }

  function markLessonComplete(status) {
    const key = lessonKey(activeModuleIndex, activeLessonIndex)
    setCompletedLessons((prev) => ({ ...prev, [key]: status }))
  }

  function handleQuizAnswer(moduleIndex, questionIndex, option) {
    const moduleKey = String(moduleIndex)
    setQuizAnswers((prev) => ({
      ...prev,
      [moduleKey]: {
        ...(prev[moduleKey] || {}),
        [questionIndex]: option,
      },
    }))
  }

  function submitQuiz(moduleIndex) {
    const module = course.modules[moduleIndex]
    const moduleKey = String(moduleIndex)
    const answers = quizAnswers[moduleKey] || {}
    let correct = 0

    module.quiz.forEach((question, questionIndex) => {
      if (answers[questionIndex] === question.answer) {
        correct += 1
      }
    })

    setQuizResults((prev) => ({
      ...prev,
      [moduleKey]: {
        score: Math.round((correct / module.quiz.length) * 100),
        correct,
        total: module.quiz.length,
        submitted: true,
      },
    }))
  }

  async function completeCourse() {
    try {
      const response = await api.completeCourse(courseId)
      const cert = await api.getCertificate(response.certificate_id)
      setCertificate(cert)
      const latest = await api.getCourse(courseId)
      setData(latest)
    } catch (err) {
      setError(err.message)
    }
  }

  if (loading) {
    return <main className="page container"><div className="card">Loading course...</div></main>
  }

  if (error) {
    return <main className="page container"><div className="alert error">{error}</div></main>
  }

  const currentLessonKey = lessonKey(activeModuleIndex, activeLessonIndex)
  const currentNotes = lessonNotes[currentLessonKey] || ''
  const currentLessonCompleted = Boolean(completedLessons[currentLessonKey])
  const currentQuizState = quizAnswers[String(activeModuleIndex)] || {}
  const currentQuizResult = quizResults[String(activeModuleIndex)]
  const currentModuleProgress = moduleProgress[activeModuleIndex] || { percent: 0, lessonCompleted: 0, lessonTotal: 0, quizDone: false }

  return (
    <main className="page container course-shell">
      <section className="card course-topbar">
        <div>
          <p className="pill">{data.target_role}</p>
          <h1>{course.title}</h1>
          <p className="subtle">{course.overview}</p>
        </div>
        <div className="course-topbar-meta">
          <p className={`status-chip ${data.status}`}>{data.status}</p>
          <div className="engine-badge small-badge">
            <span className="engine-dot" />
            <div>
              <strong>{course.generation_source === 'llm' ? 'Hugging Face LLM' : 'Fallback Generator'}</strong>
              <small>{course.model_name}</small>
            </div>
          </div>
        </div>
      </section>

      <section className="course-overview-grid section-gap">
        <div className="card compact-stat-card">
          <p className="muted-label">Track Type</p>
          <strong>{course.experience_type}</strong>
        </div>
        <div className="card compact-stat-card">
          <p className="muted-label">Estimated Duration</p>
          <strong>{course.estimated_duration}</strong>
        </div>
        <div className="card compact-stat-card">
          <p className="muted-label">Focus Topics</p>
          <strong>{course.focus_topics.join(' • ')}</strong>
        </div>
        <div className="card compact-stat-card">
          <p className="muted-label">Course Progress</p>
          <strong>{progressPercent}% complete</strong>
          <small className="subtle">{completedCount}/{totalLessons} lessons • {submittedQuizCount}/{totalQuizUnits} quizzes • {completedModuleCount}/{course.modules.length} modules complete</small>
          <div className="progress-bar"><span style={{ width: `${progressPercent}%` }} /></div>
        </div>
      </section>

      <section className="course-workspace section-gap">
        <aside className="card curriculum-panel">
          <div className="curriculum-panel-header">
            <div>
              <h3>Curriculum</h3>
              <p className="subtle">Expand modules and open a lesson to study, take notes, and finish the quiz.</p>
            </div>
          </div>

          <div className="curriculum-list">
            {course.modules.map((module, moduleIndex) => {
              const moduleMetric = moduleProgress[moduleIndex]
              return (
                <div key={module.module_number} className="curriculum-module">
                  <button className="module-toggle" onClick={() => toggleModule(moduleIndex)}>
                    <span>{expandedModules[moduleIndex] ? '▾' : '▸'}</span>
                    <div className="module-toggle-copy">
                      <div className="module-toggle-row">
                        <strong>Module {module.module_number}: {module.title}</strong>
                        <span className={`module-progress-badge ${moduleMetric.percent === 100 ? 'done' : ''}`}>{moduleMetric.percent}%</span>
                      </div>
                      <small>{module.module_summary}</small>
                      <div className="module-progress-meta">
                        <span>{moduleMetric.lessonCompleted}/{moduleMetric.lessonTotal} lessons complete</span>
                        <span>{moduleMetric.quizDone ? 'Quiz submitted' : 'Quiz pending'}</span>
                      </div>
                      <div className="progress-bar slim"><span style={{ width: `${moduleMetric.percent}%` }} /></div>
                    </div>
                  </button>

                  {expandedModules[moduleIndex] && (
                    <div className="curriculum-lessons">
                      {module.lessons.map((lesson, lessonIndex) => {
                        const key = lessonKey(moduleIndex, lessonIndex)
                        const isActive = activeModuleIndex === moduleIndex && activeLessonIndex === lessonIndex
                        return (
                          <button
                            key={`${module.module_number}-${lesson.lesson_number}`}
                            className={`lesson-chip ${isActive ? 'active' : ''}`}
                            onClick={() => selectLesson(moduleIndex, lessonIndex)}
                          >
                            <span>{completedLessons[key] ? '✓' : '•'}</span>
                            <div>
                              <strong>{lesson.title}</strong>
                              <small>{lesson.duration} • {lesson.format}</small>
                            </div>
                          </button>
                        )
                      })}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </aside>

        <section className="course-content-column">
          <div className="card lesson-panel">
            <div className="lesson-header">
              <div>
                <p className="muted-label">Module {activeModule.module_number}</p>
                <h2>{activeLesson.title}</h2>
                <p className="subtle">{activeLesson.summary}</p>
              </div>
              <div className="lesson-meta-badges">
                <span className="mini-pill">{activeLesson.duration}</span>
                <span className="mini-pill outline">{activeLesson.format}</span>
                <span className="mini-pill outline">Module progress {currentModuleProgress.percent}%</span>
              </div>
            </div>

            <div className="lesson-objectives-grid">
              <div className="lesson-objectives-card">
                <h4>Learning objectives</h4>
                <ul>
                  {activeModule.learning_objectives.map((objective) => <li key={objective}>{objective}</li>)}
                </ul>
              </div>
              <div className="lesson-objectives-card highlight-card">
                <h4>Key takeaways</h4>
                <ul>
                  {activeLesson.key_takeaways.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </div>
            </div>

            <div className="lesson-sections">
              {activeLesson.content_sections.map((section) => (
                <div key={section.heading} className="lesson-section-block">
                  <h4>{section.heading}</h4>
                  <p>{section.body}</p>
                </div>
              ))}
            </div>

            <div className="example-box">
              <h4>{activeLesson.example.title}</h4>
              <p>{activeLesson.example.scenario}</p>
              <ol>
                {activeLesson.example.steps.map((step) => <li key={step}>{step}</li>)}
              </ol>
            </div>

            <div className="practice-box">
              <h4>Practice task</h4>
              <p>{activeLesson.practice_task}</p>
            </div>

            <div className="notes-card">
              <label>
                Personal notes
                <textarea
                  rows="5"
                  value={currentNotes}
                  onChange={(e) => handleNoteChange(e.target.value)}
                  placeholder="Write your notes here..."
                />
              </label>
              <div className="lesson-actions-row">
                <button className="button-primary" onClick={() => markLessonComplete(true)}>Mark lesson as complete</button>
                <button className="button-secondary" onClick={() => markLessonComplete(false)}>Mark as not complete</button>
              </div>
              <p className="subtle status-inline">Current lesson status: {currentLessonCompleted ? 'Completed' : 'Not completed yet'}</p>
            </div>
          </div>

          <div className="card quiz-panel section-gap">
            <div className="lesson-header">
              <div>
                <h3>Module Quiz</h3>
                <p className="subtle">Quiz completion also counts toward your module and overall course progress.</p>
              </div>
              {currentQuizResult?.submitted && (
                <div className="quiz-score-badge">Score: {currentQuizResult.score}%</div>
              )}
            </div>

            <div className="assessment-list quiz-list-tight">
              {activeModule.quiz.map((question, questionIndex) => (
                <div key={question.question} className="assessment-card quiz-question-card">
                  <h4>Q{questionIndex + 1}. {question.question}</h4>
                  <div className="option-list">
                    {question.options.map((option) => (
                      <label key={option} className="option-item">
                        <input
                          type="radio"
                          name={`quiz-${activeModuleIndex}-${questionIndex}`}
                          checked={currentQuizState[questionIndex] === option}
                          onChange={() => handleQuizAnswer(activeModuleIndex, questionIndex, option)}
                        />
                        <span className="option-text">{option}</span>
                      </label>
                    ))}
                  </div>
                  {currentQuizResult?.submitted && (
                    <div className={`quiz-feedback ${currentQuizState[questionIndex] === question.answer ? 'correct' : 'incorrect'}`}>
                      <strong>Correct answer:</strong> {question.answer}<br />
                      {question.explanation}
                    </div>
                  )}
                </div>
              ))}
            </div>

            <div className="lesson-actions-row">
              <button className="button-primary" onClick={() => submitQuiz(activeModuleIndex)}>Submit quiz</button>
            </div>
          </div>

          <div className="course-bottom-grid section-gap">
            <div className="card assignment-panel">
              <h3>Module Assignment</h3>
              <p><strong>{activeModule.assignment.title}</strong></p>
              <p>{activeModule.assignment.description}</p>
              <p className="muted-label">Deliverables</p>
              <ul>
                {activeModule.assignment.deliverables.map((item) => <li key={item}>{item}</li>)}
              </ul>
              <p className="muted-label">Submission Type</p>
              <p>{activeModule.assignment.submission_type}</p>
            </div>

            <div className="card assignment-panel">
              <h3>Capstone Challenge</h3>
              <p><strong>{course.capstone.title}</strong></p>
              <p>{course.capstone.description}</p>
              <p className="muted-label">Capstone Deliverables</p>
              <ul>
                {course.capstone.deliverables.map((item) => <li key={item}>{item}</li>)}
              </ul>
              <p className="muted-label">Certificate Criteria</p>
              <ul>
                {course.certificate_criteria.map((criterion) => <li key={criterion}>{criterion}</li>)}
              </ul>
              {data.status !== 'completed' && (
                <button className="button-primary" onClick={completeCourse}>Mark Course as Completed</button>
              )}
            </div>
          </div>
        </section>
      </section>

      {certificate && (
        <section className="section-gap">
          <div className="card certificate-card">
            <p className="pill">Certificate Issued</p>
            <h2>Certificate of Completion</h2>
            <p>This certifies that <strong>{certificate.student_name}</strong> has successfully completed the course <strong>{certificate.course_title}</strong>.</p>
            <p>Certificate ID: {certificate.certificate_id}</p>
            <p>Issued At: {new Date(certificate.issued_at).toLocaleString()}</p>
          </div>
        </section>
      )}
    </main>
  )
}
