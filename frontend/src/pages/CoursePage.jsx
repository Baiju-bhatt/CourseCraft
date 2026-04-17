import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api'

function cleanText(value) {
  return String(value || '')
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/[“”]/g, '"')
    .replace(/\s+/g, ' ')
    .trim()
}

function splitIntoReadablePoints(text) {
  const cleaned = cleanText(text)
  if (!cleaned) return { intro: '', bullets: [] }
  const sentences = cleaned.split(/(?<=[.!?])\s+/).map((s) => s.trim()).filter(Boolean)
  if (sentences.length <= 2) {
    return { intro: cleaned, bullets: [] }
  }
  return { intro: sentences[0], bullets: sentences.slice(1) }
}

function lessonKey(moduleIndex, lessonIndex) {
  return `${moduleIndex}-${lessonIndex}`
}

export default function CoursePage() {
  const { courseId } = useParams()
  const [data, setData] = useState(null)
  const [certificate, setCertificate] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [expandedModules, setExpandedModules] = useState({ 0: true })
  const [activeModuleIndex, setActiveModuleIndex] = useState(0)
  const [activeLessonIndex, setActiveLessonIndex] = useState(0)
  const [lessonNotes, setLessonNotes] = useState({})
  const [completedLessons, setCompletedLessons] = useState({})
  const [quizAnswers, setQuizAnswers] = useState({})
  const [quizResults, setQuizResults] = useState({})
  const [capstoneSubmitted, setCapstoneSubmitted] = useState(false)
  const [certificateId, setCertificateId] = useState(null)
  const [isSavingProgress, setIsSavingProgress] = useState(false)
  const [downloadingPdf, setDownloadingPdf] = useState(false)
  const [downloadingSchedule, setDownloadingSchedule] = useState(false)
  const [downloadingCertificate, setDownloadingCertificate] = useState(false)
  const [scheduleForm, setScheduleForm] = useState(() => ({
    startDate: new Date(Date.now() + 86400000).toISOString().slice(0, 10),
    startTime: '19:00',
    sessionsPerWeek: 3,
    sessionMinutes: 60,
  }))
  const [videoState, setVideoState] = useState({ loading: false, videos: [], message: '', enabled: true, fallbackSearchUrl: '' })
  const [ttsSupported, setTtsSupported] = useState(false)
  const [speechVoices, setSpeechVoices] = useState([])
  const [selectedVoice, setSelectedVoice] = useState('')
  const [speechRate, setSpeechRate] = useState(1)
  const [ttsStatus, setTtsStatus] = useState('idle')
  const [ttsMessage, setTtsMessage] = useState('')
  const utteranceRef = useRef(null)
  const saveTimerRef = useRef(null)

  const course = data?.course
  const progressSummary = data?.progress_summary
  const activeModule = course?.modules?.[activeModuleIndex]
  const activeLesson = activeModule?.lessons?.[activeLessonIndex]

  function hydrateProgress(progress) {
    setLessonNotes(progress?.lesson_notes || {})
    setCompletedLessons(progress?.completed_lessons || {})
    setQuizAnswers(progress?.quiz_answers || {})
    setQuizResults(progress?.quiz_results || {})
    setCapstoneSubmitted(Boolean(progress?.capstone_submitted))
    setCertificateId(progress?.certificate_id || null)
  }

  useEffect(() => {
    let mounted = true
    setLoading(true)
    api.getCourse(courseId)
      .then((response) => {
        if (!mounted) return
        setData(response)
        hydrateProgress(response.progress || {})
        if (response.progress?.certificate_id) {
          api.getCertificate(response.progress.certificate_id).then(setCertificate).catch(() => {})
        }
      })
      .catch((err) => mounted && setError(err.message))
      .finally(() => mounted && setLoading(false))
    return () => { mounted = false }
  }, [courseId])

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'smooth' })
    stopSpeech(true)
  }, [activeModuleIndex, activeLessonIndex])

  useEffect(() => {
    if (typeof window === 'undefined' || !window.speechSynthesis) {
      setTtsSupported(false)
      return undefined
    }
    setTtsSupported(true)
    function loadVoices() {
      const availableVoices = window.speechSynthesis.getVoices() || []
      setSpeechVoices(availableVoices)
      if (!selectedVoice && availableVoices.length) {
        const englishVoice = availableVoices.find((voice) => voice.lang?.toLowerCase().startsWith('en'))
        setSelectedVoice((englishVoice || availableVoices[0]).name)
      }
    }
    loadVoices()
    window.speechSynthesis.onvoiceschanged = loadVoices
    return () => {
      window.speechSynthesis.onvoiceschanged = null
      window.speechSynthesis.cancel()
    }
  }, [selectedVoice])

  useEffect(() => {
    if (!course?.modules?.length) return
    let cancelled = false
    setVideoState((prev) => ({ ...prev, loading: true, message: '', videos: [] }))
    api.getCourseVideos(courseId, activeModuleIndex, activeLessonIndex)
      .then((response) => {
        if (cancelled) return
        setVideoState({
          loading: false,
          videos: response.videos || [],
          message: response.message || '',
          enabled: response.enabled !== false,
          fallbackSearchUrl: response.fallback_search_url || '',
        })
      })
      .catch((err) => {
        if (cancelled) return
        setVideoState({ loading: false, videos: [], message: err.message || 'Unable to load videos.', enabled: true, fallbackSearchUrl: '' })
      })
    return () => { cancelled = true }
  }, [courseId, course, activeModuleIndex, activeLessonIndex])

  const totalLessons = useMemo(() => course?.modules?.reduce((sum, module) => sum + (module.lessons?.length || 0), 0) || 0, [course])
  const totalQuizUnits = course?.modules?.length || 0
  const totalTrackUnits = totalLessons + totalQuizUnits + (course?.final_capstone || course?.capstone ? 1 : 0)

  const moduleProgress = useMemo(() => {
    if (!course?.modules) return []
    return course.modules.map((module, moduleIndex) => {
      const lessonTotal = module.lessons?.length || 0
      const lessonCompleted = module.lessons.reduce((count, _lesson, lessonIndex) => count + (completedLessons[lessonKey(moduleIndex, lessonIndex)] ? 1 : 0), 0)
      const quizState = quizResults[String(moduleIndex)] || {}
      const quizDone = Boolean(quizState.submitted)
      const quizPassed = Boolean(quizState.passed)
      const moduleComplete = lessonTotal > 0 && lessonCompleted === lessonTotal && quizPassed
      return {
        lessonCompleted,
        lessonTotal,
        quizDone,
        quizPassed,
        moduleComplete,
      }
    })
  }, [course, completedLessons, quizResults])

  const moduleProgressWithLock = useMemo(() => moduleProgress.map((item, index) => ({ ...item, unlocked: index === 0 || moduleProgress[index - 1]?.moduleComplete })), [moduleProgress])
  const completedCount = useMemo(() => Object.values(completedLessons).filter(Boolean).length, [completedLessons])
  const completedQuizCount = useMemo(() => Object.values(quizResults).filter((result) => result?.submitted).length, [quizResults])
  const completedModuleCount = useMemo(() => moduleProgressWithLock.filter((item) => item.moduleComplete).length, [moduleProgressWithLock])
  const progressPercent = totalTrackUnits ? Math.round(((completedCount + completedQuizCount + (capstoneSubmitted ? 1 : 0)) / totalTrackUnits) * 100) : 0
  const allModulesComplete = course?.modules?.length ? completedModuleCount === course.modules.length : false
  const certificateEligible = allModulesComplete && capstoneSubmitted && progressPercent >= 80

  useEffect(() => {
    if (!course || loading) return
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
    saveTimerRef.current = setTimeout(async () => {
      try {
        setIsSavingProgress(true)
        const payload = {
          lesson_notes: lessonNotes,
          completed_lessons: completedLessons,
          quiz_answers: quizAnswers,
          quiz_results: quizResults,
          capstone_submitted: capstoneSubmitted,
          certificate_id: certificateId,
        }
        const response = await api.saveCourseProgress(courseId, payload)
        setData((prev) => prev ? { ...prev, progress: response.progress, progress_summary: response.summary, status: response.summary.eligible_for_certificate ? 'completed' : prev.status } : prev)
        setCertificateId(response.progress?.certificate_id || null)
        if (response.progress?.certificate_id) {
          api.getCertificate(response.progress.certificate_id).then(setCertificate).catch(() => {})
        }
      } catch (err) {
        setError(err.message)
      } finally {
        setIsSavingProgress(false)
      }
    }, 450)
    return () => saveTimerRef.current && clearTimeout(saveTimerRef.current)
  }, [courseId, course, loading, lessonNotes, completedLessons, quizAnswers, quizResults, capstoneSubmitted])

  function stopSpeech(resetMessage = false) {
    if (typeof window === 'undefined' || !window.speechSynthesis) return
    window.speechSynthesis.cancel()
    utteranceRef.current = null
    setTtsStatus('idle')
    if (resetMessage) setTtsMessage('')
  }

  function buildLessonNarrationText(module, lesson) {
    if (!module || !lesson) return ''
    const parts = [
      `Module ${module.module_number}: ${cleanText(module.title)}.`,
      `Lesson: ${cleanText(lesson.title)}.`,
      cleanText(lesson.summary),
      ...(lesson.key_takeaways || []).map((item) => cleanText(item)),
      ...((lesson.content_sections || []).flatMap((section) => [cleanText(section.heading), cleanText(section.body)])),
      cleanText(lesson.practice_task),
    ]
    return parts.filter(Boolean).join(' ')
  }

  function selectLesson(moduleIndex, lessonIndex) {
    if (!moduleProgressWithLock[moduleIndex]?.unlocked) return
    setExpandedModules((prev) => ({ ...prev, [moduleIndex]: true }))
    setActiveModuleIndex(moduleIndex)
    setActiveLessonIndex(lessonIndex)
  }

  function toggleModule(moduleIndex) {
    if (!moduleProgressWithLock[moduleIndex]?.unlocked) return
    setExpandedModules((prev) => ({ ...prev, [moduleIndex]: !prev[moduleIndex] }))
  }

  function markLessonComplete(status) {
    const key = lessonKey(activeModuleIndex, activeLessonIndex)
    setCompletedLessons((prev) => ({ ...prev, [key]: status }))
  }

  function handleQuizAnswer(moduleIndex, questionIndex, option) {
    const moduleKey = String(moduleIndex)
    setQuizAnswers((prev) => ({ ...prev, [moduleKey]: { ...(prev[moduleKey] || {}), [questionIndex]: option } }))
  }

  function submitQuiz(moduleIndex) {
    const module = course.modules[moduleIndex]
    const moduleKey = String(moduleIndex)
    const answers = quizAnswers[moduleKey] || {}
    let correct = 0
    const details = {}
    module.quiz.forEach((question, questionIndex) => {
      const selected = answers[questionIndex] || null
      const isCorrect = selected === question.answer
      if (isCorrect) correct += 1
      details[questionIndex] = { selected, correct_answer: question.answer, is_correct: isCorrect }
    })
    const score = Math.round((correct / module.quiz.length) * 100)
    setQuizResults((prev) => ({
      ...prev,
      [moduleKey]: { score, correct, total: module.quiz.length, submitted: true, passed: score >= 60, details },
    }))
  }

  async function completeCourse() {
    try {
      const response = await api.completeCourse(courseId)
      setCertificateId(response.certificate_id)
      const cert = await api.getCertificate(response.certificate_id)
      setCertificate(cert)
      setData((prev) => prev ? { ...prev, status: 'completed' } : prev)
    } catch (err) {
      setError(err.message)
    }
  }

  async function downloadCoursePdf() {
    setError('')
    setDownloadingPdf(true)
    try { await api.downloadCoursePdf(courseId) } catch (err) { setError(err.message) } finally { setDownloadingPdf(false) }
  }

  function updateScheduleForm(field, value) {
    setScheduleForm((prev) => ({ ...prev, [field]: value }))
  }

  async function downloadCourseSchedule() {
    setError('')
    setDownloadingSchedule(true)
    try {
      await api.downloadCourseSchedule(courseId, {
        start_date: scheduleForm.startDate,
        start_time: scheduleForm.startTime,
        sessions_per_week: scheduleForm.sessionsPerWeek,
        session_minutes: scheduleForm.sessionMinutes,
      })
    } catch (err) { setError(err.message) } finally { setDownloadingSchedule(false) }
  }

  async function handleReadAloud() {
    if (!ttsSupported || !activeLesson) return
    const narrationText = buildLessonNarrationText(activeModule, activeLesson)
    if (!narrationText) return
    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(narrationText)
    const selected = speechVoices.find((voice) => voice.name === selectedVoice)
    if (selected) { utterance.voice = selected; utterance.lang = selected.lang } else { utterance.lang = 'en-US' }
    utterance.rate = Number(speechRate)
    utterance.onstart = () => { setTtsStatus('speaking'); setTtsMessage(`Now reading ${cleanText(activeLesson.title)}`) }
    utterance.onpause = () => { setTtsStatus('paused'); setTtsMessage('Playback paused.') }
    utterance.onresume = () => { setTtsStatus('speaking'); setTtsMessage(`Now reading ${cleanText(activeLesson.title)}`) }
    utterance.onend = () => { utteranceRef.current = null; setTtsStatus('idle'); setTtsMessage('Finished reading this lesson.') }
    utterance.onerror = () => { utteranceRef.current = null; setTtsStatus('idle'); setTtsMessage('Unable to play text-to-speech for this lesson right now.') }
    utteranceRef.current = utterance
    window.speechSynthesis.speak(utterance)
  }

  if (loading) return <main className="page container"><div className="card">Loading course...</div></main>
  if (error && !data) return <main className="page container"><div className="alert error">{error}</div></main>

  const currentLessonKey = lessonKey(activeModuleIndex, activeLessonIndex)
  const currentNotes = lessonNotes[currentLessonKey] || ''
  const currentLessonCompleted = Boolean(completedLessons[currentLessonKey])
  const currentQuizState = quizAnswers[String(activeModuleIndex)] || {}
  const currentQuizResult = quizResults[String(activeModuleIndex)]
  const currentModuleProgress = moduleProgressWithLock[activeModuleIndex] || { percent: 0, lessonCompleted: 0, lessonTotal: 0, quizDone: false }
  const isLastLessonInModule = activeLessonIndex === (activeModule?.lessons?.length || 1) - 1
  const canAttemptQuiz = currentModuleProgress.lessonCompleted === currentModuleProgress.lessonTotal && isLastLessonInModule
  const capstone = course.final_capstone || course.capstone

  return (
    <main className="page container course-shell">
      {error && <div className="alert error">{error}</div>}
      <section className="card course-topbar">
        <div>
          <p className="pill">{data.target_role}</p>
          <h1>{cleanText(course.title)}</h1>
          <p className="subtle">{cleanText(course.overview)}</p>
        </div>
        <div className="course-topbar-meta">
          <button type="button" className="button-secondary" onClick={downloadCoursePdf} disabled={downloadingPdf}>{downloadingPdf ? 'Preparing PDF...' : 'Download Course PDF'}</button>
        </div>
      </section>


      <section className="section-gap">
        <div className="card schedule-config-card">
          <div className="lesson-header">
            <div>
              <h3>Study Schedule Export</h3>
              <p className="subtle">Configure the Outlook-compatible .ics file before downloading your study plan.</p>
            </div>
            <button type="button" className="button-secondary" onClick={downloadCourseSchedule} disabled={downloadingSchedule}>
              {downloadingSchedule ? 'Preparing Schedule...' : 'Download Outlook ICS'}
            </button>
          </div>
          <div className="schedule-form-grid">
            <label>
              Start Date
              <input type="date" value={scheduleForm.startDate} onChange={(e) => updateScheduleForm('startDate', e.target.value)} />
            </label>
            <label>
              Start Time
              <input type="time" value={scheduleForm.startTime} onChange={(e) => updateScheduleForm('startTime', e.target.value)} />
            </label>
            <label>
              Sessions Per Week
              <input type="number" min="1" max="7" value={scheduleForm.sessionsPerWeek} onChange={(e) => updateScheduleForm('sessionsPerWeek', e.target.value)} />
            </label>
            <label>
              Minutes Per Session
              <input type="number" min="15" step="15" value={scheduleForm.sessionMinutes} onChange={(e) => updateScheduleForm('sessionMinutes', e.target.value)} />
            </label>
          </div>
        </div>
      </section>

      <section className="course-overview-grid section-gap">
        <div className="card compact-stat-card"><p className="muted-label">Track Type</p><strong>{cleanText(course.experience_type)}</strong></div>
        <div className="card compact-stat-card"><p className="muted-label">Estimated Duration</p><strong>{cleanText(course.estimated_duration)}</strong></div>
        <div className="card compact-stat-card"><p className="muted-label">Focus Topics</p><strong>{course.focus_topics.map(cleanText).join(' • ')}</strong></div>
        <div className="card compact-stat-card">
          <p className="muted-label">Course Progress</p>
          <strong>{progressPercent}% complete</strong>
          <small className="subtle">{completedCount}/{totalLessons} lessons • {completedQuizCount}/{totalQuizUnits} quizzes • {completedModuleCount}/{course.modules.length} modules • {isSavingProgress ? 'Saving…' : 'Saved'}</small>
          <div className="progress-bar"><span style={{ width: `${progressPercent}%` }} /></div>
        </div>
      </section>

      <section className="course-workspace section-gap">
        <aside className="card curriculum-panel">
          <div className="curriculum-panel-header"><div><h3>Curriculum</h3><p className="subtle">Expand modules and open a lesson to study, take notes, and finish the quiz.</p></div></div>
          <div className="curriculum-list scrollable-panel">
            {course.modules.map((module, moduleIndex) => {
              const metric = moduleProgressWithLock[moduleIndex]
              const isUnlocked = Boolean(metric?.unlocked)
              return (
                <div key={module.module_number} className={`curriculum-module ${!isUnlocked ? 'locked-module' : ''}`}>
                  <button className="module-toggle" onClick={() => toggleModule(moduleIndex)}>
                    <span>{expandedModules[moduleIndex] ? '▾' : '▸'}</span>
                    <div className="module-toggle-copy">
                      <div className="module-toggle-row">
                        <strong>Module {module.module_number}: {cleanText(module.title)}</strong>
                        <span className={`module-progress-badge ${metric?.moduleComplete ? 'done' : ''}`}>{metric?.moduleComplete ? 'Done' : !isUnlocked ? 'Locked' : `${Math.round(((metric.lessonCompleted + (metric.quizDone ? 1 : 0)) / Math.max(1, metric.lessonTotal + 1)) * 100)}%`}</span>
                      </div>
                      <small>{cleanText(module.module_summary)}</small>
                      <div className="module-progress-meta"><span>{metric?.lessonCompleted}/{metric?.lessonTotal} lessons complete</span><span>{metric?.quizPassed ? 'Quiz passed' : metric?.quizDone ? 'Quiz attempted' : 'Quiz pending'}</span></div>
                      <div className="progress-bar slim"><span style={{ width: `${Math.round(((metric.lessonCompleted + (metric.quizDone ? 1 : 0)) / Math.max(1, metric.lessonTotal + 1)) * 100)}%` }} /></div>
                    </div>
                  </button>
                  {expandedModules[moduleIndex] && isUnlocked && (
                    <div className="curriculum-lessons">
                      {module.lessons.map((lesson, lessonIndex) => {
                        const key = lessonKey(moduleIndex, lessonIndex)
                        const isActive = activeModuleIndex === moduleIndex && activeLessonIndex === lessonIndex
                        return (
                          <button key={`${module.module_number}-${lesson.lesson_number}`} className={`lesson-chip ${isActive ? 'active' : ''}`} onClick={() => selectLesson(moduleIndex, lessonIndex)}>
                            <span>{completedLessons[key] ? '✓' : '•'}</span>
                            <div><strong>{cleanText(lesson.title)}</strong><small>{cleanText(lesson.duration)} • {cleanText(lesson.format)}</small></div>
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
              <div><p className="muted-label">Module {activeModule.module_number}</p><h2>{cleanText(activeLesson.title)}</h2><p className="subtle">{cleanText(activeLesson.summary)}</p></div>
              <div className="lesson-meta-badges"><span className="mini-pill">{cleanText(activeLesson.duration)}</span><span className="mini-pill outline">{cleanText(activeLesson.format)}</span><span className="mini-pill outline">Module progress {Math.round(((currentModuleProgress.lessonCompleted + (currentModuleProgress.quizDone ? 1 : 0)) / Math.max(1, currentModuleProgress.lessonTotal + 1)) * 100)}%</span></div>
            </div>

            <div className="lesson-objectives-grid">
              <div className="lesson-objectives-card"><h4>Learning objectives</h4><ul>{activeModule.learning_objectives.map((objective) => <li key={objective}>{cleanText(objective)}</li>)}</ul></div>
              <div className="lesson-objectives-card highlight-card"><h4>Key takeaways</h4><ul>{activeLesson.key_takeaways.map((item) => <li key={item}>{cleanText(item)}</li>)}</ul></div>
            </div>

            <div className="lesson-sections">
              {activeLesson.content_sections.map((section) => {
                const content = splitIntoReadablePoints(section.body)
                return (
                  <div key={section.heading} className="lesson-section-block">
                    <h4>{cleanText(section.heading)}</h4>
                    {content.intro && <p>{content.intro}</p>}
                    {content.bullets.length > 0 && <ul>{content.bullets.map((point) => <li key={point}>{point}</li>)}</ul>}
                  </div>
                )
              })}
            </div>

            <div className="example-box"><h4>{cleanText(activeLesson.example.title)}</h4><p>{cleanText(activeLesson.example.scenario)}</p><ol>{activeLesson.example.steps.map((step) => <li key={step}>{cleanText(step)}</li>)}</ol></div>
            <div className="practice-box"><h4>Practice task</h4><p>{cleanText(activeLesson.practice_task)}</p></div>

            <div className="card lesson-audio-panel embedded-card formal-panel">
              <div className="lesson-header"><div><h3>Audio Lesson Assistant</h3><p className="subtle">Listen to the active lesson in a polished read-aloud mode while you review the material.</p></div><span className={`mini-pill outline ${ttsStatus === 'speaking' ? 'tts-pill-active' : ''}`}>{ttsStatus === 'speaking' ? 'Playing' : ttsStatus === 'paused' ? 'Paused' : 'Ready'}</span></div>
              <div className="tts-toolbar">
                <label className="tts-control"><span className="muted-label">Voice</span><select value={selectedVoice} onChange={(e) => setSelectedVoice(e.target.value)} disabled={!ttsSupported || ttsStatus === 'speaking'}>{!speechVoices.length && <option value="">Default voice</option>}{speechVoices.map((voice) => <option key={`${voice.name}-${voice.lang}`} value={voice.name}>{voice.name} ({voice.lang})</option>)}</select></label>
                <label className="tts-control tts-rate-control"><span className="muted-label">Playback speed</span><select value={speechRate} onChange={(e) => setSpeechRate(Number(e.target.value))}><option value={0.8}>0.8x</option><option value={1}>1.0x</option><option value={1.15}>1.15x</option><option value={1.3}>1.3x</option></select></label>
              </div>
              <div className="lesson-actions-row tts-actions-row"><button className="button-primary" type="button" onClick={handleReadAloud} disabled={!ttsSupported}>Start audio</button><button className="button-secondary" type="button" onClick={() => window.speechSynthesis?.pause()} disabled={ttsStatus !== 'speaking'}>Pause</button><button className="button-secondary" type="button" onClick={() => window.speechSynthesis?.resume()} disabled={ttsStatus !== 'paused'}>Resume</button><button className="button-secondary" type="button" onClick={() => stopSpeech(false)} disabled={ttsStatus === 'idle'}>Stop</button></div>
              {!ttsSupported && <div className="video-message-box warning"><p className="subtle video-warning">Text-to-speech is not supported in this browser. Try Chrome, Edge, or Safari.</p></div>}
              {ttsSupported && ttsMessage && <div className="tts-message-box"><p className="subtle">{ttsMessage}</p></div>}
            </div>

            <div className="card lesson-video-panel embedded-card formal-panel">
              <div className="lesson-header"><div><h3>Recommended Learning Videos</h3><p className="subtle">Curated video suggestions matched to the current lesson topic.</p></div></div>
              {videoState.loading && <p className="subtle">Loading recommended videos...</p>}
              {!videoState.loading && videoState.message && <div className={`video-message-box ${videoState.enabled === false ? 'warning' : ''}`}><p className={`subtle ${videoState.enabled === false ? 'video-warning' : ''}`}>{videoState.message}</p>{videoState.enabled === false && videoState.fallbackSearchUrl && <a className="button-secondary video-link-button" href={videoState.fallbackSearchUrl} target="_blank" rel="noreferrer">Open YouTube search</a>}</div>}
              {!videoState.loading && videoState.videos.length > 0 && <div className="video-grid">{videoState.videos.map((video) => <article key={video.video_id} className="video-card"><div className="video-frame-wrap"><iframe src={video.embed_url} title={video.title} loading="lazy" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowFullScreen /></div><div className="video-card-body"><h4>{cleanText(video.title)}</h4><p className="subtle video-meta-text">{cleanText(video.channel_title)}{video.duration ? ` • ${video.duration}` : ''}</p><p className="subtle video-description">{cleanText(video.description || 'Relevant video resource for this lesson.')}</p><a className="button-secondary video-link-button" href={video.watch_url} target="_blank" rel="noreferrer">Open on YouTube</a></div></article>)}</div>}
            </div>

            <div className="notes-card"><label>Personal notes<textarea rows="5" value={currentNotes} onChange={(e) => setLessonNotes((prev) => ({ ...prev, [currentLessonKey]: e.target.value }))} placeholder="Write your notes here..." /></label><div className="lesson-actions-row"><button className="button-primary" onClick={() => markLessonComplete(true)}>Mark lesson as complete</button><button className="button-secondary" onClick={() => markLessonComplete(false)}>Mark as not complete</button></div><p className="subtle status-inline">Current lesson status: {currentLessonCompleted ? 'Completed' : 'Not completed yet'}</p></div>
          </div>

          <div className="card quiz-panel section-gap">
            <div className="lesson-header"><div><h3>Module Quiz</h3><p className="subtle">Finish every lesson in this module, then pass the quiz with at least 60% to unlock the next module.</p></div>{currentQuizResult?.submitted && <div className="quiz-score-badge">Score: {currentQuizResult.score}% · {currentQuizResult.correct}/{currentQuizResult.total} correct</div>}</div>
            {!canAttemptQuiz ? <div className="video-message-box warning"><p className="subtle">Complete every lesson in this module and open the final lesson to unlock the quiz.</p></div> : <div className="assessment-list quiz-list-tight">{activeModule.quiz.map((question, questionIndex) => <div key={`${question.question}-${questionIndex}`} className="assessment-card quiz-question-card"><div className="question-meta-row"><h4>Q{questionIndex + 1}. {cleanText(question.question)}</h4><span className={`difficulty-badge ${String(question.difficulty || 'Medium').toLowerCase()}`}>{question.difficulty || 'Medium'}</span></div><div className="option-list">{question.options.map((option) => { const detail = currentQuizResult?.details?.[questionIndex]; const optionState = currentQuizResult?.submitted ? option === question.answer ? 'correct-option' : detail?.selected === option ? 'incorrect-option' : '' : ''; return <label key={`${option}-${questionIndex}`} className={`option-item ${optionState}`}><input type="radio" name={`quiz-${activeModuleIndex}-${questionIndex}`} checked={currentQuizState[questionIndex] === option} onChange={() => handleQuizAnswer(activeModuleIndex, questionIndex, option)} /><span className="option-text">{cleanText(option)}</span></label>})}</div>{currentQuizResult?.submitted && <div className={`quiz-feedback ${currentQuizResult?.details?.[questionIndex]?.is_correct ? 'correct' : 'incorrect'}`}><strong>{currentQuizResult?.details?.[questionIndex]?.is_correct ? 'Correct' : 'Not quite'}</strong><br /><strong>Correct answer:</strong> {cleanText(question.answer)}<br />{cleanText(question.explanation)}</div>}</div>)}</div>}
            {canAttemptQuiz && <div className="lesson-actions-row"><button className="button-primary" onClick={() => submitQuiz(activeModuleIndex)}>{currentQuizResult?.submitted ? 'Recheck quiz' : 'Submit quiz'}</button></div>}
          </div>

          <div className="course-bottom-grid section-gap">
            <div className="card assignment-panel"><h3>Module Assignment</h3><p><strong>{cleanText(activeModule.assignment.title)}</strong></p><p>{cleanText(activeModule.assignment.description)}</p><p className="muted-label">Deliverables</p><ul>{activeModule.assignment.deliverables.map((item) => <li key={item}>{cleanText(item)}</li>)}</ul><p className="muted-label">Submission Type</p><p>{cleanText(activeModule.assignment.submission_type)}</p></div>

            {allModulesComplete && capstone && <div className="card assignment-panel capstone-panel"><h3>Final Capstone Project</h3><p><strong>{cleanText(capstone.title)}</strong></p><p>{cleanText(capstone.description)}</p>{capstone.project_goal && <><p className="muted-label">Project Goal</p><p>{cleanText(capstone.project_goal)}</p></>}{capstone.scenario && <><p className="muted-label">Scenario</p><p>{cleanText(capstone.scenario)}</p></>}{capstone.required_sections?.length > 0 && <><p className="muted-label">What your PDF must include</p><ul>{capstone.required_sections.map((item) => <li key={item}>{cleanText(item)}</li>)}</ul></>}{capstone.deliverables?.length > 0 && <><p className="muted-label">Deliverables</p><ul>{capstone.deliverables.map((item) => <li key={item}>{cleanText(item)}</li>)}</ul></>}{capstone.submission_rules?.length > 0 && <><p className="muted-label">Submission Rules</p><ul>{capstone.submission_rules.map((item) => <li key={item}>{cleanText(item)}</li>)}</ul></>}{capstone.evaluation_rubric?.length > 0 && <><p className="muted-label">How it will be evaluated</p><ul>{capstone.evaluation_rubric.map((item) => <li key={item}>{cleanText(item)}</li>)}</ul></>}<div className="lesson-actions-row"><button className="button-secondary" onClick={() => setCapstoneSubmitted((prev) => !prev)}>{capstoneSubmitted ? 'Mark capstone as not submitted' : 'Mark capstone PDF as submitted'}</button>{certificateEligible && data.status !== 'completed' && <button className="button-primary" onClick={completeCourse}>Issue Certificate</button>}</div></div>}
          </div>
        </section>
      </section>

      {(certificate || certificateId) && <section className="section-gap"><div className="card certificate-card"><p className="pill">Certificate Issued</p><h2>Certificate of Completion</h2><p>This certifies that <strong>{cleanText(certificate?.student_name || JSON.parse(localStorage.getItem('user') || '{}').full_name || '')}</strong> has successfully completed the course <strong>{cleanText(certificate?.course_title || course.title)}</strong>.</p><p>Certificate ID: {certificate?.certificate_id || certificateId}</p>{certificate?.issued_at && <p>Issued At: {new Date(certificate.issued_at).toLocaleString()}</p>}<div className="lesson-actions-row"><button className="button-primary" onClick={async () => { setDownloadingCertificate(true); try { await api.downloadCertificate(certificate?.certificate_id || certificateId) } catch (err) { setError(err.message) } finally { setDownloadingCertificate(false) } }} disabled={downloadingCertificate}>{downloadingCertificate ? 'Preparing Certificate...' : 'Download Certificate PDF'}</button></div></div></section>}
    </main>
  )
}
