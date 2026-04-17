const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api'

function getToken() {
  return localStorage.getItem('token')
}

function notifyAuthChanged() {
  window.dispatchEvent(new Event('auth-change'))
}

export class AuthError extends Error {
  constructor(message = 'Session expired. Please log in again.') {
    super(message)
    this.name = 'AuthError'
    this.status = 401
  }
}

async function parseResponse(response) {
  const contentType = response.headers.get('content-type') || ''
  if (contentType.includes('application/json')) {
    return response.json().catch(() => ({}))
  }
  const text = await response.text().catch(() => '')
  return text ? { message: text } : {}
}

async function request(path, options = {}) {
  const headers = {
    ...(options.headers || {}),
  }

  if (!(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json'
  }

  const token = getToken()
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  let response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers,
    })
  } catch (error) {
    throw new Error('Unable to reach the server. Please try again later.')
  }

  const data = await parseResponse(response)

  if (response.status === 401) {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    notifyAuthChanged()
    throw new AuthError(data.error || 'Session expired. Please log in again.')
  }

  if (!response.ok) {
    throw new Error(data.error || data.message || 'Something went wrong')
  }

  return data
}

export { notifyAuthChanged }

async function download(path, fallbackFilename) {
  const headers = {}
  const token = getToken()
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  let response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { headers })
  } catch (error) {
    throw new Error('Unable to reach the server. Please try again later.')
  }

  if (response.status === 401) {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    notifyAuthChanged()
    throw new AuthError()
  }

  if (!response.ok) {
    const data = await parseResponse(response)
    throw new Error(data.error || data.message || 'Download failed')
  }

  const blob = await response.blob()
  const disposition = response.headers.get('content-disposition') || ''
  const filenameMatch = disposition.match(/filename="?([^";]+)"?/)
  const filename = filenameMatch?.[1] || fallbackFilename || 'download'

  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(url)
  return { filename }
}

export const api = {
  getConfig: () => request('/config'),
  register: (payload) => request('/auth/register', { method: 'POST', body: JSON.stringify(payload) }),
  login: (payload) => request('/auth/login', { method: 'POST', body: JSON.stringify(payload) }),
  adminLogin: (payload) => request('/admin/login', { method: 'POST', body: JSON.stringify(payload) }),
  getDashboard: () => request('/dashboard/summary'),
  getAssessmentQuestions: (payload) => request('/assessment/questions', { method: 'POST', body: JSON.stringify(payload) }),
  evaluateAssessment: (payload) => request('/assessment/evaluate', { method: 'POST', body: JSON.stringify(payload) }),
  generateCourse: (payload) => request('/course/generate', { method: 'POST', body: JSON.stringify(payload) }),
  getMyCourses: () => request('/course/my-courses'),
  getCourse: (courseId) => request(`/course/${courseId}`),
  getCourseProgress: (courseId) => request(`/course/${courseId}/progress`),
  saveCourseProgress: (courseId, payload) => request(`/course/${courseId}/progress`, { method: 'PUT', body: JSON.stringify(payload) }),
  getCourseVideos: (courseId, moduleIndex, lessonIndex) => request(`/course/${courseId}/videos?module_index=${moduleIndex}&lesson_index=${lessonIndex}`),
  downloadCoursePdf: (courseId) => download(`/course/${courseId}/export-pdf`, 'course.pdf'),
  downloadCourseSchedule: (courseId, params) => {
    const search = new URLSearchParams(params).toString()
    return download(`/course/${courseId}/export-schedule?${search}`, 'course_schedule.ics')
  },
  completeCourse: (courseId) => request(`/course/${courseId}/complete`, { method: 'POST' }),
  getCertificate: (certificateId) => request(`/certificate/${certificateId}`),
  downloadCertificate: (certificateId) => download(`/certificate/${certificateId}/download`, `certificate_${certificateId}.pdf`),
  getAdminSummary: () => request('/admin/summary'),
  getAdminTable: (tableName) => request(`/admin/${tableName}`),
  createAdminRecord: (tableName, payload) => request(`/admin/${tableName}`, { method: 'POST', body: JSON.stringify(payload) }),
  updateAdminRecord: (tableName, recordId, payload) => request(`/admin/${tableName}/${recordId}`, { method: 'PUT', body: JSON.stringify(payload) }),
  deleteAdminRecord: (tableName, recordId) => request(`/admin/${tableName}/${recordId}`, { method: 'DELETE' }),
  chat: (message, history = [], topicContext = '') =>
    request('/chat', {
      method: 'POST',
      body: JSON.stringify({ message, history, topic_context: topicContext }),
    }),
  listFiles: () => request('/files'),
  uploadFile: (file) => {
    const form = new FormData()
    form.append('file', file)
    return request('/files/upload', { method: 'POST', body: form })
  },
  previewFile: (filename) => request(`/files/${encodeURIComponent(filename)}/preview`),
  runCode: (payload) => request('/code/run', { method: 'POST', body: JSON.stringify(payload) }),
}
