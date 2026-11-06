const STEPS = [
  { message: 'Cloning repository & preparing workspace...', progress: 18 },
  { message: 'Running multithreaded AST & security scans...', progress: 56 },
  { message: 'Computing unified ELKjs architecture layout...', progress: 82 },
  { message: 'Rendering graph...', progress: 96 },
];

function stageFor({ loading, status, layoutStatus }) {
  if (loading) {
    if (['queued', 'cloning'].includes(status)) return 0;
    return 1;
  }
  if (layoutStatus === 'layout') return 2;
  if (layoutStatus === 'rendering') return 3;
  return -1;
}

export default function JobStatus({ loading, status, layoutStatus, error }) {
  if (error) return <p className="notice error" role="alert">{error}</p>;

  const stage = stageFor({ loading, status, layoutStatus });
  const visible = stage >= 0;
  const current = STEPS[Math.max(0, stage)];

  return (
    <section
      className={`analysis-progress${visible ? ' analysis-progress--visible' : ''}`}
      aria-hidden={!visible}
      aria-live="polite"
      aria-label="Repository analysis progress"
    >
      <div className="analysis-progress__card">
        <span className="analysis-progress__spinner" aria-hidden="true" />
        <div className="analysis-progress__content">
          <div className="analysis-progress__meta">
            <span>ANALYSIS IN PROGRESS</span>
            <span>STEP {Math.max(1, stage + 1)} OF {STEPS.length}</span>
          </div>
          <p className="analysis-progress__message">{current.message}</p>
          <div
            className="analysis-progress__track"
            role="progressbar"
            aria-valuemin="0"
            aria-valuemax="100"
            aria-valuenow={current.progress}
            aria-label={current.message}
          >
            <span style={{ width: `${current.progress}%` }} />
          </div>
        </div>
      </div>
    </section>
  );
}
