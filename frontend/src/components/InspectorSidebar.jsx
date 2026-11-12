import LanguageBadge from './LanguageBadge.jsx';

export default function InspectorSidebar({ analysis, selectedFile }) {
  const metadata = analysis.file_metadata?.[selectedFile];
  // AI Summary UI can be re-enabled by uncommenting this line and its JSX below.
  // const summary = analysis.ai_summaries?.[selectedFile];
  const fanMetrics = analysis.graph_metrics?.fan?.[selectedFile] || {};
  const routes = metadata?.routes || [];
  const risks = [
    ...(analysis.security_findings || []).filter((finding) => finding.file === selectedFile),
    ...(metadata?.security_warnings || []),
  ].filter((risk, index, all) => all.findIndex((other) => other.type === risk.type && other.line === risk.line) === index);
  const classifications = metadata?.classifications || [metadata?.classification || 'source'];

  return (
    <aside className="inspector" aria-label="Selected file details">
      <p className="eyebrow">INSPECTOR</p>
      <h2>{selectedFile || 'Select a file'}</h2>
      {metadata?.error ? <p className="error-text">{metadata.error}</p> : metadata ? (
        <>
          <div className="inspector-language-row">
            <LanguageBadge filePath={selectedFile} fileType={metadata.file_type} />
            <span className="inspector-file-type">File type: {metadata.file_type || 'source'}</span>
          </div>
          <div className="classification-list">
            {classifications.map((role) => (
              <span className={`classification${role === 'infrastructure' || role === 'config' ? ' classification--infrastructure' : ''}`} key={role}>{role}</span>
            ))}
          </div>
          <div className="detail">
            <h3>Module dependencies</h3>
            <div className="fan-metrics">
              <div><span>Fan-in</span><strong>{fanMetrics.fan_in ?? 0}</strong></div>
              <div><span>Fan-out</span><strong>{fanMetrics.fan_out ?? 0}</strong></div>
            </div>
          </div>
          <Detail label="Classes" values={metadata.classes} />
          <Detail label="Functions" values={metadata.functions} />
          <Detail label="Model fields" values={(metadata.symbols || []).flatMap((symbol) => (symbol.fields || []).map((field) => `${symbol.name}.${field}`))} />
          <Detail label="Internal imports" values={metadata.internal_imports} />
          <Detail label="External imports" values={metadata.external_imports} />
          <div className="detail">
            <h3>Routes</h3>
            {routes.length ? routes.map((route) => <p key={`${route.name}:${route.line}:${route.method}`}>{route.method} {route.path || '(path not literal)'} · L{route.line}</p>) : <p>None detected</p>}
          </div>
          <div className="detail">
            <h3>Security findings <span className="finding-count">{risks.length}</span></h3>
            {risks.length ? risks.map((risk, index) => <p className="risk-line" key={`${risk.type}:${risk.line}:${index}`}><strong>{risk.severity || 'review'}</strong> · {risk.type} · L{risk.line}{risk.message ? ` — ${risk.message}` : ''}</p>) : <p>None detected</p>}
          </div>
          {/* AI Summary UI temporarily disabled; preserve it for later.
          <div className="summary"><h3>AI summary</h3><p>{summary || 'No AI summary is available for this file.'}</p></div>
          */}
        </>
      ) : <p className="empty-state">Choose a file to inspect its extracted metadata.</p>}
    </aside>
  );
}

function Detail({ label, values = [] }) {
  const labels = values.map((value) => (typeof value === 'string' ? value : value.name || JSON.stringify(value)));
  return <div className="detail"><h3>{label}</h3><p>{labels.length ? labels.join(', ') : 'None detected'}</p></div>;
}
