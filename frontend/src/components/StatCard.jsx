export default function StatCard({ label, value }) {
  return (
    <div className="card stat-card">
      <p className="muted-label">{label}</p>
      <h3>{value}</h3>
    </div>
  )
}
