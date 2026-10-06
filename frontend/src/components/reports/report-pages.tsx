"use client";
import { ProjectGate } from "@/components/common/project-gate";
import { ReportList } from "@/components/reports/monthly-reports";

export function ReportListPage() {
  return <ProjectGate>{(p) => <ReportList project={p} />}</ProjectGate>;
}
