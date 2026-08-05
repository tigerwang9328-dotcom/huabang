declare module "@/utils/mumarenVoucherLineSummary.mjs" {
  interface VoucherLineSummarySource {
    key: string;
    summary?: string | null;
  }

  interface ResolvedVoucherLineSummaries {
    previewByKey: Record<string, string>;
    savedByKey: Record<string, string>;
  }

  export function resolveVoucherLineSummaries(
    lines: VoucherLineSummarySource[],
    clearedKeys: Set<string>,
  ): ResolvedVoucherLineSummaries;
}
