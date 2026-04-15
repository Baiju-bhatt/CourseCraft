import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import StatCard from '../components/StatCard'

const PRETTY_LABELS = {
  users: 'Users',
  courses: 'Courses',
  assessment_attempts: 'Assessment Attempts',
  certificates: 'Certificates',
}

function getRecordId(row) {
  return row.id
}

function toFormValue(value) {
  if (value === null || value === undefined) return ''
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  return String(value)
}

export default function AdminPortalPage() {
  const [summary, setSummary] = useState(null)
  const [selectedTable, setSelectedTable] = useState('users')
  const [tableData, setTableData] = useState(null)
  const [formMode, setFormMode] = useState('create')
  const [formValues, setFormValues] = useState({})
  const [editingId, setEditingId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  async function loadSummary() {
    const data = await api.getAdminSummary()
    setSummary(data)
    if (!selectedTable && data.tables?.length) {
      setSelectedTable(data.tables[0].name)
    }
    return data
  }

  async function loadTable(tableName) {
    setLoading(true)
    setError('')
    setMessage('')
    try {
      const data = await api.getAdminTable(tableName)
      setTableData(data)
      setFormMode('create')
      setEditingId(null)
      setFormValues({})
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadSummary()
      .then((data) => loadTable(selectedTable || data.tables?.[0]?.name || 'users'))
      .catch((err) => {
        setError(err.message)
        setLoading(false)
      })
  }, [])

  useEffect(() => {
    if (summary && selectedTable) {
      loadTable(selectedTable)
    }
  }, [selectedTable])

  const activeTableConfig = useMemo(() => {
    return summary?.tables?.find((item) => item.name === selectedTable) || null
  }, [summary, selectedTable])

  const formFields = formMode === 'edit'
    ? [...(activeTableConfig?.editable_fields || []), ...(selectedTable === 'users' ? ['password'] : [])]
    : (activeTableConfig?.create_fields || [])

  function resetForm() {
    setFormMode('create')
    setEditingId(null)
    setFormValues({})
    setMessage('')
    setError('')
  }

  function startEdit(row) {
    const initial = {}
    formFields.forEach((field) => {
      if (field === 'password') return
      const prettyKey = `${field}_pretty`
      initial[field] = prettyKey in row ? toFormValue(row[prettyKey]) : toFormValue(row[field])
    })
    setFormMode('edit')
    setEditingId(getRecordId(row))
    setFormValues(initial)
    setMessage('')
    setError('')
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    setMessage('')

    const payload = {}
    for (const [key, value] of Object.entries(formValues)) {
      if (value !== '') payload[key] = value
    }

    try {
      if (formMode === 'edit' && editingId !== null) {
        const response = await api.updateAdminRecord(selectedTable, editingId, payload)
        setMessage(response.message)
      } else {
        const response = await api.createAdminRecord(selectedTable, payload)
        setMessage(response.message)
      }
      await loadSummary()
      await loadTable(selectedTable)
      resetForm()
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  async function handleDelete(row) {
    const recordId = getRecordId(row)
    const confirmed = window.confirm(`Delete this record from ${PRETTY_LABELS[selectedTable] || selectedTable}?`)
    if (!confirmed) return
    setError('')
    setMessage('')
    try {
      const response = await api.deleteAdminRecord(selectedTable, recordId)
      setMessage(response.message)
      await loadSummary()
      await loadTable(selectedTable)
      if (editingId === recordId) {
        resetForm()
      }
    } catch (err) {
      setError(err.message)
    }
  }

  if (!summary && loading) {
    return <main className="page container"><div className="card">Loading admin portal...</div></main>
  }

  return (
    <main className="page container admin-page">
      <section className="page-heading-row">
        <div>
          <div className="pill">Administrator</div>
          <h1>Admin Portal</h1>
          <p className="subtle">Manage database records, monitor system usage, and maintain platform data from one workspace.</p>
        </div>
      </section>

      {summary && (
        <section className="admin-stats-grid section-gap">
          <StatCard label="Total Users" value={summary.stats.total_users} />
          <StatCard label="Admin Users" value={summary.stats.admin_users} />
          <StatCard label="Courses" value={summary.stats.total_courses} />
          <StatCard label="Completed Courses" value={summary.stats.completed_courses} />
          <StatCard label="Assessments" value={summary.stats.assessment_attempts} />
          <StatCard label="Certificates" value={summary.stats.certificates_issued} />
        </section>
      )}

      <section className="admin-layout section-gap">
        <aside className="card admin-sidebar">
          <h3>Tables</h3>
          <div className="admin-table-nav">
            {summary?.tables?.map((table) => (
              <button
                key={table.name}
                type="button"
                className={`admin-nav-button ${selectedTable === table.name ? 'active' : ''}`}
                onClick={() => setSelectedTable(table.name)}
              >
                <span>{table.label}</span>
                <small>{table.fields.length} fields</small>
              </button>
            ))}
          </div>
          <div className="admin-help-box">
            <h4>What you can do</h4>
            <ul className="compact-list">
              <li>Create new rows directly in the selected table.</li>
              <li>Edit current records without leaving the portal.</li>
              <li>Delete records when cleanup is required.</li>
              <li>Review JSON fields in readable text format.</li>
            </ul>
          </div>
        </aside>

        <section className="admin-main-stack">
          <div className="card admin-form-card">
            <div className="admin-card-header">
              <div>
                <h3>{formMode === 'edit' ? `Edit ${PRETTY_LABELS[selectedTable] || selectedTable}` : `Create ${PRETTY_LABELS[selectedTable] || selectedTable}`}</h3>
                <p className="subtle">Use this form to {formMode === 'edit' ? 'update the selected record' : 'add a new record'} in the database.</p>
              </div>
              {formMode === 'edit' && <button type="button" className="button-secondary" onClick={resetForm}>Cancel Edit</button>}
            </div>

            <form className="form-grid two-column" onSubmit={handleSubmit}>
              {formFields.map((field) => {
                const isTextArea = field.endsWith('_json') || field === 'password'
                const value = formValues[field] ?? ''
                return (
                  <label key={field} className={isTextArea ? 'full-span' : ''}>
                    {field}
                    {isTextArea ? (
                      <textarea rows="6" value={value} onChange={(e) => setFormValues((prev) => ({ ...prev, [field]: e.target.value }))} />
                    ) : (
                      <input value={value} onChange={(e) => setFormValues((prev) => ({ ...prev, [field]: e.target.value }))} />
                    )}
                  </label>
                )
              })}
              {error && <div className="alert error full-span">{error}</div>}
              {message && <div className="alert success full-span">{message}</div>}
              <div className="full-span admin-form-actions">
                <button type="submit" className="button-primary" disabled={submitting}>{submitting ? 'Saving...' : formMode === 'edit' ? 'Update Record' : 'Create Record'}</button>
                <button type="button" className="button-secondary" onClick={() => loadTable(selectedTable)} disabled={submitting}>Refresh Table</button>
              </div>
            </form>
          </div>

          <div className="card admin-table-card">
            <div className="admin-card-header">
              <div>
                <h3>{tableData?.label || PRETTY_LABELS[selectedTable] || selectedTable}</h3>
                <p className="subtle">Showing up to 200 records from the selected table.</p>
              </div>
            </div>

            {loading ? (
              <div className="subtle">Loading table...</div>
            ) : !tableData?.rows?.length ? (
              <div className="subtle">No records found in this table.</div>
            ) : (
              <div className="admin-record-stack">
                {tableData.rows.map((row) => (
                  <article key={getRecordId(row)} className="admin-record-card">
                    <div className="admin-record-actions">
                      <button type="button" className="button-secondary" onClick={() => startEdit(row)}>Edit</button>
                      <button type="button" className="ghost-button danger-outline" onClick={() => handleDelete(row)}>Delete</button>
                    </div>
                    <div className="admin-record-grid">
                      {tableData.fields.map((field) => {
                        const displayValue = row[`${field}_pretty`] ?? row[field]
                        return (
                          <div key={field} className="admin-record-field">
                            <span className="admin-field-label">{field}</span>
                            <pre className="admin-field-value">{displayValue === null || displayValue === undefined || displayValue === '' ? '—' : String(displayValue)}</pre>
                          </div>
                        )
                      })}
                    </div>
                  </article>
                ))}
              </div>
            )}
          </div>
        </section>
      </section>
    </main>
  )
}
