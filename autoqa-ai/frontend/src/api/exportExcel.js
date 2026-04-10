import * as XLSX from 'xlsx';

function flattenValue(val) {
  if (val === null || val === undefined) return '';
  if (typeof val === 'string') return val;
  if (Array.isArray(val)) return val.map(v => flattenValue(v)).join('\n');
  if (typeof val === 'object') return Object.entries(val).map(([k, v]) => `${k}: ${v}`).join('\n');
  return String(val);
}

/**
 * Export multiple sheets to a single Excel file.
 * @param {Array<{sheetName: string, rows: Array<object>}>} sheets
 * @param {string} filename  e.g. "test-cases.xlsx"
 */
export function exportToExcel(sheets, filename = 'export.xlsx') {
  const wb = XLSX.utils.book_new();

  sheets.forEach(({ sheetName, rows }) => {
    if (!rows || rows.length === 0) return;

    // Flatten all values so objects/arrays become readable strings
    const flat = rows.map((row, i) => {
      const out = { '#': i + 1 };
      Object.entries(row).forEach(([k, v]) => { out[k] = flattenValue(v); });
      return out;
    });

    const ws = XLSX.utils.json_to_sheet(flat);

    // Auto column widths
    const cols = Object.keys(flat[0]);
    ws['!cols'] = cols.map(col => ({
      wch: Math.min(60, Math.max(col.length + 2, ...flat.map(r => String(r[col] || '').length)))
    }));

    XLSX.utils.book_append_sheet(wb, ws, sheetName.slice(0, 31));
  });

  XLSX.writeFile(wb, filename);
}
