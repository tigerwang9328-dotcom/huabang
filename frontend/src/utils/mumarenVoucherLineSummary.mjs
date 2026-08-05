/**
 * Derive display previews and persistence values without mutating voucher lines.
 * A cleared row is deliberately blank only for that row; it does not reset the
 * preceding manual summary for rows below it.
 */
export function resolveVoucherLineSummaries(lines, clearedKeys) {
  let latestManualSummary = "";
  const previewByKey = {};
  const savedByKey = {};

  for (const line of lines) {
    const manualSummary = String(line.summary || "").trim();
    if (manualSummary) latestManualSummary = manualSummary;

    const explicitlyCleared = clearedKeys.has(line.key);
    const inheritedSummary = !manualSummary && !explicitlyCleared ? latestManualSummary : "";
    previewByKey[line.key] = inheritedSummary;
    savedByKey[line.key] = manualSummary || inheritedSummary;
  }

  return { previewByKey, savedByKey };
}
