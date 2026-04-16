const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000/api'

function getToken() {
  return localStorage.getItem('token')
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

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  })

  const data = await parseResponse(response)

  if (response.status === 401) {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    throw new AuthError(data.error || 'Session expired. Please log in again.')
  }

  if (!response.ok) {
    throw new Error(data.error || data.message || 'Something went wrong')
  }

  return data
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
  completeCourse: (courseId) => request(`/course/${courseId}/complete`, { method: 'POST' }),
  getCertificate: (certificateId) => request(`/certificate/${certificateId}`),
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
