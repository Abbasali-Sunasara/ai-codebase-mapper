import { Workflow } from 'lucide-react';

export default function Header() {
  return <header className="page-header flex items-start justify-between"><div><p className="eyebrow"><Workflow size={14} /> CODEBASE EXPLORER</p><h1>AI Codebase Mapper</h1><p>Explore deterministic code structure with concise AI explanations.</p></div></header>;
}
