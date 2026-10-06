"use client";
import { useTranslations } from "next-intl";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { PageHeader } from "@/components/common/page-header";
import { ProjectById, ProjectGate } from "@/components/common/project-gate";
import { ErrorState, LoadingState } from "@/components/common/states";
import { WorkforceForm } from "@/components/workforce/workforce-form";
import { ImportReport, WorkforceImportPage } from "@/components/workforce/workforce-import";
import { WorkforceList } from "@/components/workforce/workforce-list";
import { WorkforceMonths } from "@/components/workforce/workforce-months";
import { useWorkforceReturn } from "@/lib/api/hse";

export function WorkforceListPage() {
  return <ProjectGate>{(p) => <WorkforceList project={p} />}</ProjectGate>;
}

export function WorkforceCreatePage() {
  const t = useTranslations("workforce");
  const tn = useTranslations("nav");
  return (
    <div>
      <Breadcrumbs items={[{ label: tn("workforce"), href: "/workforce" }, { label: t("createTitle") }]} />
      <PageHeader title={t("createTitle")} />
      <ProjectGate>{(p) => <WorkforceForm project={p} />}</ProjectGate>
    </div>
  );
}

export function WorkforceEditPage({ id }: { id: string }) {
  const t = useTranslations("workforce");
  const tn = useTranslations("nav");
  const q = useWorkforceReturn(id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const r = q.data;
  return (
    <div>
      <Breadcrumbs items={[{ label: tn("workforce"), href: "/workforce" }, { label: t("detailTitle"), href: `/workforce/${r.id}` }, { label: t("editTitle") }]} />
      <PageHeader title={t("editTitle")} />
      <ProjectById id={r.project_id}>{(p) => <WorkforceForm project={p} ret={r} />}</ProjectById>
    </div>
  );
}

export function WorkforceImportRoute() {
  return <ProjectGate>{(p) => <WorkforceImportPage project={p} />}</ProjectGate>;
}

export function WorkforceImportReportRoute({ id }: { id: string }) {
  return <ImportReport id={id} />;
}

export function WorkforceMonthsPage() {
  return <ProjectGate>{(p) => <WorkforceMonths project={p} />}</ProjectGate>;
}
