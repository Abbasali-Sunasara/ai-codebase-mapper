import { getLanguageBadgeStyle, getLanguageInfo } from '../lib/language.js';

export default function LanguageBadge({ filePath, fileType, compact = false }) {
  const language = getLanguageInfo(filePath, fileType);
  if (!language) return null;

  return (
    <span
      className={`language-badge${compact ? ' language-badge--compact' : ''}`}
      style={getLanguageBadgeStyle(language)}
      title={language.label}
    >
      {compact ? language.short : language.label}
    </span>
  );
}
