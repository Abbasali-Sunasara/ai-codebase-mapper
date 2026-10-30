import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';
const apiClient = axios.create({ baseURL: API_BASE_URL, headers: { 'Content-Type': 'application/json' } });

export async function analyzeRepository(repoUrl, onStatus = () => {}) {
  const { data: job } = await apiClient.post('/api/analyze', { repo_url: repoUrl });
  let status = job.status;
  while (!['done', 'error'].includes(status)) {
    onStatus(status);
    await new Promise((resolve) => window.setTimeout(resolve, 1200));
    const response = await apiClient.get(`/api/jobs/${job.job_id}`);
    status = response.data.status;
    if (status === 'done') return response.data.result;
    if (status === 'error') throw new Error(response.data.error || 'Analysis failed.');
  }
  throw new Error('Analysis job ended without a result.');
}
