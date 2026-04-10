import React from 'react';

export default function ScoreBadge({ score }) {
  const style =
    score >= 80 ? 'bg-emerald-50 text-emerald-700 border-emerald-200' :
    score >= 50 ? 'bg-amber-50 text-amber-700 border-amber-200' :
                  'bg-red-50 text-red-700 border-red-200';
  return (
    <span className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold border ${style}`}>
      Score: {score} / 100
    </span>
  );
}
