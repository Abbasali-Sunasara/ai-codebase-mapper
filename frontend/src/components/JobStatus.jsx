const labels = { queued: 'Queued for analysis…', cloning: 'Cloning repository…', parsing: 'Parsing source files…', analyzing: 'Building the graph…', summarizing: 'Writing component summaries…' };

export default function JobStatus({ loading, status, error }) {
  if (loading) return <p className="notice" role="status">{labels[status] || 'Analysis in progress…'}</p>;
  if (error) return <p className="notice error" role="alert">{error}</p>;
  return null;
}
