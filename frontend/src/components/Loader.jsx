import React from 'react';

export default function Loader({ message = 'AI is analyzing...' }) {
  return (
    <div className="flex flex-col items-center justify-center py-14 gap-3">
      <div className="w-9 h-9 border-[3px] border-blue-200 border-t-blue-600 rounded-full animate-spin" />
      <p className="text-slate-500 text-sm">{message}</p>
    </div>
  );
}
