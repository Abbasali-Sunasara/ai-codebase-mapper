export default function MetricsPanel({ analysis }) {
  const files = Object.entries(analysis.file_metadata || {}).filter(([path, metadata]) => (
    metadata.file_type === 'python' || (!metadata.file_type && path.endsWith('.py'))
  )).length;
  const metrics = analysis.graph_metrics || {};
  const risks = analysis.security_findings || [];
  const fanValues = Object.values(metrics.fan || {});
  const maxFanIn = Math.max(0, ...fanValues.map((value) => value.fan_in));
  const maxFanOut = Math.max(0, ...fanValues.map((value) => value.fan_out));
  return <section className="metrics" aria-label="Repository metrics"><article><span>Python files</span><strong>{files}</strong></article><article><span>Components</span><strong>{analysis.component_nodes_count || 0}</strong></article><article><span>Dependencies</span><strong>{analysis.edges_count}</strong></article><article><span>Cycles</span><strong>{metrics.cycles_truncated ? `${metrics.cycles.length}+` : metrics.cycles?.length || 0}</strong></article><article><span>Largest fan-in</span><strong>{maxFanIn}</strong></article><article><span>Largest fan-out</span><strong>{maxFanOut}</strong></article><article><span>Large modules</span><strong>{metrics.oversized_modules?.length || 0}</strong></article><article><span>Security flags</span><strong>{risks.length}</strong></article></section>;
}
