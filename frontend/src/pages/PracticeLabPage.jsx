import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'

const DEFAULT_CODE = `import pandas as pd

# Example 1: simple Python
numbers = [4, 7, 11]
print('Sum:', sum(numbers))

# Example 2: use an uploaded file
# If you uploaded a CSV or XLSX file, uncomment and update the file name below.
# df = pd.read_csv('your_file.csv')
# print(df.head())
`

export default function PracticeLabPage() {
  const [code, setCode] = useState(DEFAULT_CODE)
  const [files, setFiles] = useState([])
  const [selectedFiles, setSelectedFiles] = useState([])
  const [preview, setPreview] = useState(null)
  const [output, setOutput] = useState({ status: 'idle', stdout: '', stderr: '', available_files: [] })
  const [loadingFiles, setLoadingFiles] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  async function loadFiles() {
    setLoadingFiles(true)
    try {
      const data = await api.listFiles()
      setFiles(data.files || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoadingFiles(false)
    }
  }

  useEffect(() => {
    loadFiles()
  }, [])

  async function handleUpload(event) {
    const file = event.target.files?.[0]
    if (!file) return
    setUploading(true)
    setError('')
    setSuccess('')
    try {
      const data = await api.uploadFile(file)
      setSuccess(data.message)
      await loadFiles()
      if (data.file?.name) {
        setSelectedFiles((prev) => Array.from(new Set([...prev, data.file.name])))
      }
      if (data.preview) {
        setPreview({ file: data.file?.name, ...data.preview })
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setUploading(false)
      event.target.value = ''
    }
  }

  async function handlePreview(filename) {
    setError('')
    try {
      const data = await api.previewFile(filename)
      setPreview({ file: data.file, ...data.preview })
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleRunCode() {
    setRunning(true)
    setError('')
    setSuccess('')
    try {
      const data = await api.runCode({ code, files: selectedFiles })
      setOutput(data)
    } catch (err) {
      setError(err.message)
      setOutput({ status: 'error', stdout: '', stderr: '', available_files: [] })
    } finally {
      setRunning(false)
    }
  }

  function toggleSelectedFile(filename) {
    setSelectedFiles((prev) => (
      prev.includes(filename)
        ? prev.filter((item) => item !== filename)
        : [...prev, filename]
    ))
  }

  const previewColumns = preview?.columns || []
  const previewRows = preview?.rows || []
  const statusLabel = useMemo(() => {
    if (output.status === 'timeout') return 'Execution timed out'
    if (output.status === 'error') return 'Execution finished with errors'
    if (output.status === 'ok') return 'Execution completed successfully'
    return 'Ready'
  }, [output.status])

  return (
    <main className="page container practice-page">
      <section className="page-heading-row">
        <div>
          <div className="pill">Hands-on Practice Lab</div>
          <h1>Python code editor</h1>
          <p className="subtle">Write Python, run it safely, and optionally work with uploaded CSV or XLSX files.</p>
        </div>
        <button type="button" className="button-primary" onClick={handleRunCode} disabled={running}>
          {running ? 'Running...' : 'Run Python Code'}
        </button>
      </section>

      {(error || success) && (
        <section className="section-gap">
          {error && <div className="alert error">{error}</div>}
          {success && <div className="alert success">{success}</div>}
        </section>
      )}

      <section className="practice-layout section-gap">
        <div className="practice-main-stack">
          <div className="card">
            <div className="admin-card-header">
              <div>
                <h3>Python Editor</h3>
                <p className="subtle">You can use pandas, numpy, csv, json, math, statistics, and openpyxl. File-system and network operations are blocked.</p>
              </div>
              <button type="button" className="button-secondary" onClick={() => setCode(DEFAULT_CODE)}>Reset template</button>
            </div>
            <textarea
              className="code-editor"
              value={code}
              onChange={(event) => setCode(event.target.value)}
              spellCheck="false"
            />
          </div>

          <div className="card output-card">
            <div className="admin-card-header">
              <div>
                <h3>Output Console</h3>
                <p className="subtle">{statusLabel}</p>
              </div>
            </div>
            {output.available_files?.length > 0 && (
              <div className="execution-files subtle">
                Available in runtime: {output.available_files.join(', ')}
              </div>
            )}
            <div className="console-grid">
              <div>
                <p className="muted-label">Standard Output</p>
                <pre className="console-box">{output.stdout || 'No stdout yet.'}</pre>
              </div>
              <div>
                <p className="muted-label">Errors / Traceback</p>
                <pre className="console-box error-console">{output.stderr || 'No errors.'}</pre>
              </div>
            </div>
          </div>
        </div>

        <aside className="practice-sidebar">
          <div className="card">
            <h3>Datasets</h3>
            <p className="subtle">Upload CSV or XLSX files and select which ones should be available during execution.</p>
            <label className="upload-button">
              <input type="file" accept=".csv,.xlsx" onChange={handleUpload} hidden />
              {uploading ? 'Uploading...' : 'Upload CSV / XLSX'}
            </label>
            <div className="dataset-list">
              {loadingFiles ? (
                <p className="subtle">Loading files...</p>
              ) : files.length === 0 ? (
                <p className="subtle">No datasets uploaded yet.</p>
              ) : files.map((file) => (
                <div key={file.name} className={`dataset-row ${selectedFiles.includes(file.name) ? 'selected' : ''}`}>
                  <label className="dataset-checkbox-row">
                    <input
                      type="checkbox"
                      checked={selectedFiles.includes(file.name)}
                      onChange={() => toggleSelectedFile(file.name)}
                    />
                    <span>
                      <strong>{file.name}</strong>
                      <small>{Math.round(file.size / 1024)} KB • {file.extension}</small>
                    </span>
                  </label>
                  <button type="button" className="ghost-button small-button" onClick={() => handlePreview(file.name)}>Preview</button>
                </div>
              ))}
            </div>
          </div>

          <div className="card">
            <h3>Quick Tips</h3>
            <ul className="compact-list">
              <li>Use uploaded file names exactly as shown in the dataset list.</li>
              <li>Example: <code>pd.read_csv('sales.csv')</code></li>
              <li>Excel example: <code>pd.read_excel('report.xlsx')</code></li>
              <li>Keep code focused on learning, transformation, and analysis tasks.</li>
            </ul>
          </div>

          <div className="card preview-card">
            <h3>Dataset Preview</h3>
            {!preview ? (
              <p className="subtle">Choose a file and click Preview to inspect its first rows.</p>
            ) : (
              <>
                <p className="subtle">{preview.file} • {preview.row_count} rows • {preview.column_count} columns</p>
                <div className="preview-table-wrap">
                  <table className="preview-table">
                    <thead>
                      <tr>
                        {previewColumns.map((column) => <th key={column}>{column}</th>)}
                      </tr>
                    </thead>
                    <tbody>
                      {previewRows.map((row, rowIndex) => (
                        <tr key={rowIndex}>
                          {previewColumns.map((column) => <td key={`${rowIndex}-${column}`}>{String(row[column] ?? '')}</td>)}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>
        </aside>
      </section>
    </main>
  )
}
