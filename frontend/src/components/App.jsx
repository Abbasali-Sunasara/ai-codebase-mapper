import { useState } from 'react';
import Header from './Header.jsx';
import JobStatus from './JobStatus.jsx';
import FlowCanvas from './FlowCanvas.jsx';
import InspectorSidebar from './InspectorSidebar.jsx';
import MetricsPanel from './MetricsPanel.jsx';
import { analyzeRepository } from '../services/api.js';

export default function App() {
  const [repoUrl, setRepoUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [jobStatus, setJobStatus] = useState('');
  const [layoutStatus, setLayoutStatus] = useState('idle');
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);
  const [selectedFile, setSelectedFile] = useState('');

  async function handleSubmit(event) {
    event.preventDefault();
    setLoading(true);
    setJobStatus('queued');
    setLayoutStatus('idle');
    setError('');
    setResult(null);
    setSelectedFile('');
    try {
      const data = await analyzeRepository(repoUrl.trim(), setJobStatus);
      setLayoutStatus('layout');
      setResult(data);
      setSelectedFile(Object.keys(data.analysis.file_metadata)[0] || '');
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to analyze repository. Please check the URL and backend status.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="app-shell min-h-screen">
      <Header />
      <form className="repo-form" onSubmit={handleSubmit}>
        <input type="url" value={repoUrl} onChange={(event) => setRepoUrl(event.target.value)} placeholder="https://github.com/owner/repository" required aria-label="GitHub repository URL" />
        <button type="submit" disabled={loading}>{loading ? 'Analyzing…' : 'Map architecture'}</button>
      </form>
      <JobStatus loading={loading} status={jobStatus} layoutStatus={layoutStatus} error={error} />
      {result && <>
        <MetricsPanel analysis={result.analysis} />
        <section className="workspace">
          <FlowCanvas analysis={result.analysis} selectedFile={selectedFile} onSelectFile={setSelectedFile} onLayoutStatusChange={setLayoutStatus} />
          <InspectorSidebar analysis={result.analysis} selectedFile={selectedFile} />
        </section>
      </>}
    </main>
  );
}
