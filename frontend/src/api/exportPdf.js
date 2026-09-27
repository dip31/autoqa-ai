import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';

export function exportReportPDF(result, user = null) {
  const doc = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
  const W = doc.internal.pageSize.getWidth();
  const score = result.quality_score ?? 0;

  // ── Header banner ──────────────────────────────────────────────────────────
  doc.setFillColor(37, 99, 235);          // blue-600
  doc.rect(0, 0, W, 38, 'F');
  doc.setFillColor(109, 40, 217);         // violet-700 accent strip
  doc.rect(W - 40, 0, 40, 38, 'F');

  doc.setTextColor(255, 255, 255);
  doc.setFontSize(20);
  doc.setFont('helvetica', 'bold');
  doc.text('AutoQA AI', 14, 16);
  doc.setFontSize(10);
  doc.setFont('helvetica', 'normal');
  doc.text('Smart QA Report', 14, 24);
  doc.text(`Generated: ${new Date().toLocaleDateString('en-US', { year:'numeric', month:'long', day:'numeric' })}`, 14, 31);

  // User info
  if (user?.username) {
    doc.setFontSize(9);
    doc.text(`Prepared for: ${user.username}${user.email ? '  ·  ' + user.email : ''}`, 14, 37);
  }

  // Score badge top-right
  doc.setFontSize(22);
  doc.setFont('helvetica', 'bold');
  doc.text(`${score}`, W - 28, 18, { align: 'center' });
  doc.setFontSize(8);
  doc.setFont('helvetica', 'normal');
  doc.text('/ 100', W - 28, 25, { align: 'center' });
  doc.text('Quality Score', W - 28, 31, { align: 'center' });

  let y = 48;

  // ── Score bar ──────────────────────────────────────────────────────────────
  doc.setTextColor(30, 41, 59);
  doc.setFontSize(11);
  doc.setFont('helvetica', 'bold');
  doc.text('Overall Quality Score', 14, y);
  y += 6;

  // Background bar
  doc.setFillColor(226, 232, 240);
  doc.roundedRect(14, y, W - 28, 6, 3, 3, 'F');
  // Score fill
  const fillW = Math.max(6, ((W - 28) * score) / 100);
  const [r, g, b] = score >= 80 ? [16,185,129] : score >= 50 ? [245,158,11] : [239,68,68];
  doc.setFillColor(r, g, b);
  doc.roundedRect(14, y, fillW, 6, 3, 3, 'F');
  y += 14;

  // ── Stats grid ─────────────────────────────────────────────────────────────
  const stats = [
    ['Test Cases Reviewed', result.stats?.total_testcases ?? 0],
    ['Code Reviews',        result.stats?.total_code_reviews ?? 0],
    ['Website Tests',       result.stats?.total_website_tests ?? 0],
    ['Avg TC Score',        result.stats?.avg_testcase_score ?? 0],
    ['Avg Code Score',      result.stats?.avg_code_score ?? 0],
  ];

  const colW = (W - 28) / stats.length;
  stats.forEach(([label, val], i) => {
    const x = 14 + i * colW;
    doc.setFillColor(248, 250, 252);
    doc.setDrawColor(226, 232, 240);
    doc.roundedRect(x, y, colW - 2, 18, 2, 2, 'FD');
    doc.setTextColor(37, 99, 235);
    doc.setFontSize(14);
    doc.setFont('helvetica', 'bold');
    doc.text(String(val), x + (colW - 2) / 2, y + 9, { align: 'center' });
    doc.setTextColor(100, 116, 139);
    doc.setFontSize(7);
    doc.setFont('helvetica', 'normal');
    doc.text(label, x + (colW - 2) / 2, y + 15, { align: 'center' });
  });
  y += 26;

  // ── Section helper ─────────────────────────────────────────────────────────
  const section = (title, content) => {
    if (!content) return;
    if (y > 250) { doc.addPage(); y = 20; }
    doc.setFillColor(239, 246, 255);
    doc.setDrawColor(191, 219, 254);
    doc.roundedRect(14, y, W - 28, 7, 2, 2, 'FD');
    doc.setTextColor(37, 99, 235);
    doc.setFontSize(9);
    doc.setFont('helvetica', 'bold');
    doc.text(title.toUpperCase(), 18, y + 5);
    y += 11;
    doc.setTextColor(51, 65, 85);
    doc.setFontSize(9);
    doc.setFont('helvetica', 'normal');
    const lines = doc.splitTextToSize(content, W - 28);
    lines.forEach(line => {
      if (y > 270) { doc.addPage(); y = 20; }
      doc.text(line, 14, y);
      y += 5;
    });
    y += 4;
  };

  section('Executive Summary',      result.executive_summary);
  section('Test Coverage Analysis',  result.test_coverage_analysis);
  section('Bug Summary',             result.bug_summary);

  // ── Recommendations table ──────────────────────────────────────────────────
  if (result.recommendations?.length > 0) {
    if (y > 230) { doc.addPage(); y = 20; }
    doc.setFillColor(239, 246, 255);
    doc.setDrawColor(191, 219, 254);
    doc.roundedRect(14, y, W - 28, 7, 2, 2, 'FD');
    doc.setTextColor(37, 99, 235);
    doc.setFontSize(9);
    doc.setFont('helvetica', 'bold');
    doc.text('RECOMMENDATIONS', 18, y + 5);
    y += 5;

    autoTable(doc, {
      startY: y + 4,
      head: [['#', 'Recommendation']],
      body: result.recommendations.map((r, i) => [i + 1, typeof r === 'string' ? r : JSON.stringify(r)]),
      styles: { fontSize: 8, cellPadding: 3 },
      headStyles: { fillColor: [37, 99, 235], textColor: 255, fontStyle: 'bold' },
      alternateRowStyles: { fillColor: [248, 250, 252] },
      columnStyles: { 0: { cellWidth: 10, halign: 'center' } },
      margin: { left: 14, right: 14 },
    });
    y = doc.lastAutoTable.finalY + 8;
  }

  // ── Footer ─────────────────────────────────────────────────────────────────
  const pageCount = doc.internal.getNumberOfPages();
  for (let i = 1; i <= pageCount; i++) {
    doc.setPage(i);
    doc.setFillColor(248, 250, 252);
    doc.rect(0, 285, W, 12, 'F');
    doc.setTextColor(148, 163, 184);
    doc.setFontSize(7);
    doc.setFont('helvetica', 'normal');
    doc.text(`AutoQA AI — Intelligent QA Automation Platform${user?.username ? '  ·  ' + user.username : ''}`, 14, 292);
    doc.text(`Page ${i} of ${pageCount}`, W - 14, 292, { align: 'right' });
  }

  doc.save('autoqa-smart-report.pdf');
}
