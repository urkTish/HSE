"use client";
import { useTranslations } from "next-intl";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { PageHeader } from "@/components/common/page-header";
import { ProjectById, ProjectGate } from "@/components/common/project-gate";
import { ErrorState, LoadingState } from "@/components/common/states";
import { CaseForm } from "@/components/incidents/case-form";
import { IncidentForm } from "@/components/incidents/incident-form";
import { ExcludedCases, IncidentList } from "@/components/incidents/incident-list";
import { useIncident, useInjuryCase } from "@/lib/api/hse";

export function IncidentListPage() {
  return <ProjectGate>{(p) => <IncidentList project={p} />}</ProjectGate>;
}

export function ExcludedCasesPage() {
  return <ProjectGate>{(p) => <ExcludedCases project={p} />}</ProjectGate>;
}

export function IncidentCreatePage() {
  const t = useTranslations("incidents");
  const tn = useTranslations("nav");
  return (
    <div>
      <Breadcrumbs items={[{ label: tn("incidents"), href: "/incidents" }, { label: t("createTitle") }]} />
      <PageHeader title={t("createTitle")} />
      <ProjectGate>{(p) => <IncidentForm project={p} />}</ProjectGate>
    </div>
  );
}

export function IncidentEditPage({ id }: { id: string }) {
  const t = useTranslations("incidents");
  const tn = useTranslations("nav");
  const q = useIncident(id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const r = q.data;
  return (
    <div>
      <Breadcrumbs items={[{ label: tn("incidents"), href: "/incidents" }, { label: r.ref, href: `/incidents/${r.id}` }, { label: t("editTitle") }]} />
      <PageHeader title={t("editTitle")} />
      <ProjectById id={r.project_id}>{(p) => <IncidentForm project={p} incident={r} />}</ProjectById>
    </div>
  );
}

export function CaseCreatePage({ id }: { id: string }) {
  const t = useTranslations("cases");
  const tn = useTranslations("nav");
  const q = useIncident(id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const r = q.data;
  return (
    <div>
      <Breadcrumbs items={[{ label: tn("incidents"), href: "/incidents" }, { label: r.ref, href: `/incidents/${r.id}` }, { label: t("createTitle") }]} />
      <PageHeader title={t("createTitle")} />
      <CaseForm incident={r} />
    </div>
  );
}

export function CaseEditPage({ id }: { id: string }) {
  const t = useTranslations("cases");
  const tn = useTranslations("nav");
  const c = useInjuryCase(id);
  const q = useIncident(c.data?.incident_id ?? "");
  if (c.isError) return <ErrorState error={c.error} onRetry={() => c.refetch()} />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!c.data || !q.data) return <LoadingState />;
  return (
    <div>
      <Breadcrumbs
        items={[
          { label: tn("incidents"), href: "/incidents" },
          { label: q.data.ref, href: `/incidents/${q.data.id}` },
          { label: c.data.case_no, href: `/injury-cases/${c.data.id}` },
          { label: t("editTitle") },
        ]}
      />
      <PageHeader title={t("editTitle")} />
      <CaseForm incident={q.data} kase={c.data} />
    </div>
  );
}
