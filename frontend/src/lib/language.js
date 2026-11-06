const LANGUAGE_BY_EXTENSION = {
  py: { key: 'python', label: 'Python', short: 'PY', color: '#93c5fd', background: 'rgba(30, 64, 175, .22)', border: 'rgba(96, 165, 250, .42)' },
  js: { key: 'javascript', label: 'JavaScript', short: 'JS', color: '#fde68a', background: 'rgba(161, 98, 7, .22)', border: 'rgba(250, 204, 21, .42)' },
  jsx: { key: 'javascript', label: 'JavaScript', short: 'JS', color: '#fde68a', background: 'rgba(161, 98, 7, .22)', border: 'rgba(250, 204, 21, .42)' },
  mjs: { key: 'javascript', label: 'JavaScript', short: 'JS', color: '#fde68a', background: 'rgba(161, 98, 7, .22)', border: 'rgba(250, 204, 21, .42)' },
  cjs: { key: 'javascript', label: 'JavaScript', short: 'JS', color: '#fde68a', background: 'rgba(161, 98, 7, .22)', border: 'rgba(250, 204, 21, .42)' },
  ts: { key: 'typescript', label: 'TypeScript', short: 'TS', color: '#fde68a', background: 'rgba(161, 98, 7, .22)', border: 'rgba(250, 204, 21, .42)' },
  tsx: { key: 'typescript', label: 'TypeScript', short: 'TS', color: '#fde68a', background: 'rgba(161, 98, 7, .22)', border: 'rgba(250, 204, 21, .42)' },
  c: { key: 'c', label: 'C', short: 'C', color: '#d8b4fe', background: 'rgba(107, 33, 168, .24)', border: 'rgba(192, 132, 252, .42)' },
  h: { key: 'c', label: 'C', short: 'C', color: '#d8b4fe', background: 'rgba(107, 33, 168, .24)', border: 'rgba(192, 132, 252, .42)' },
  cpp: { key: 'cpp', label: 'C++', short: 'C++', color: '#d8b4fe', background: 'rgba(107, 33, 168, .24)', border: 'rgba(192, 132, 252, .42)' },
  hpp: { key: 'cpp', label: 'C++', short: 'C++', color: '#d8b4fe', background: 'rgba(107, 33, 168, .24)', border: 'rgba(192, 132, 252, .42)' },
  cc: { key: 'cpp', label: 'C++', short: 'C++', color: '#d8b4fe', background: 'rgba(107, 33, 168, .24)', border: 'rgba(192, 132, 252, .42)' },
  java: { key: 'java', label: 'Java', short: 'JAVA', color: '#fdba74', background: 'rgba(154, 52, 18, .24)', border: 'rgba(251, 146, 60, .42)' },
  yml: { key: 'yaml', label: 'YAML', short: 'YAML', color: '#cbd5e1', background: 'rgba(71, 85, 105, .24)', border: 'rgba(148, 163, 184, .34)' },
  yaml: { key: 'yaml', label: 'YAML', short: 'YAML', color: '#cbd5e1', background: 'rgba(71, 85, 105, .24)', border: 'rgba(148, 163, 184, .34)' },
};

const LANGUAGE_BY_TYPE = {
  python: 'py', javascript: 'js', typescript: 'ts', tsx: 'tsx',
  c: 'c', cpp: 'cpp', java: 'java', yaml: 'yaml', yml: 'yml',
};

export function getLanguageInfo(filePath, fileType) {
  const typeKey = String(fileType || '').toLowerCase();
  const extension = String(filePath || '').split('.').pop()?.toLowerCase();
  const typeExtension = LANGUAGE_BY_TYPE[typeKey];
  return LANGUAGE_BY_EXTENSION[typeExtension] || LANGUAGE_BY_EXTENSION[extension] || null;
}

export function getLanguageBadgeStyle(language) {
  return {
    color: language.color,
    backgroundColor: language.background,
    borderColor: language.border,
  };
}
