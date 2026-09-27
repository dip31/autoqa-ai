import React from 'react';
import { MdErrorOutline, MdClose } from 'react-icons/md';

export default function ErrorAlert({ message, onClose }) {
  if (!message) return null;
  return (
    <div className="flex items-start gap-3 bg-red-50 border border-red-200 text-red-700 rounded-lg p-4 text-sm mb-4">
      <MdErrorOutline className="text-red-500 text-lg shrink-0 mt-0.5" />
      <p className="flex-1">{message}</p>
      {onClose && (
        <button onClick={onClose} className="text-red-400 hover:text-red-600 shrink-0">
          <MdClose />
        </button>
      )}
    </div>
  );
}
