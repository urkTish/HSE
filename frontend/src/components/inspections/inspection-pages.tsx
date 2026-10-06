"use client";
import { useTranslations } from "next-intl";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { PageHeader } from "@/components/common/page-header";
import { ProjectById, ProjectGate } from "@/components/common/project-gate";
import { ErrorState, LoadingState } from "@/components/common/states";
import { InspectionList, PlanForm, PlanList, UnplannedInspectionForm } from "@/components/inspections/inspections";
import { useInspectionPlan } from "@/lib/api/hse";

export function InspectionListPage() {
  return <ProjectGate>{(p) => <InspectionList project={p} />}</ProjectGate>;
}

export function UnplannedInspectionPage() {
  const t = useTranslations("inspections");
  const tn = useTranslations("nav");
  return (
    <div>
      <Breadcrumbs items={[{ label: tn("inspections"), href: "/inspections" }, { label: t("unplanned") }]} />
      <PageHeader title={t("unplanned")} />
      <ProjectGate>{(p) => <UnplannedInspectionForm project={p} />}</ProjectGate>
    </div>
  );
}

export function PlanListPage() {
  return <ProjectGate>{(p) => <PlanList project={p} />}</ProjectGate>;
}

export function PlanCreatePage() {
  const t = useTranslations("inspections");
  const tn = useTranslations("nav");
  return (
    <div>
      <Breadcrumbs items={[{ label: tn("inspections"), href: "/inspections" }, { label: t("plans"), href: "/inspection-plans" }, { label: t("newPlan") }]} />
      <PageHeader title={t("newPlan")} />
      <ProjectGate>{(p) => <PlanForm project={p} />}</ProjectGate>
    </div>
  );
}

export function PlanEditPage({ id }: { id: string }) {
  const t = useTranslations("inspections");
  const tn = useTranslations("nav");
  const q = useInspectionPlan(id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const plan = q.data;
  return (
    <div>
      <Breadcrumbs items={[{ label: tn("inspections"), href: "/inspections" }, { label: t("plans"), href: "/inspection-plans" }, { label: t("editPlan") }]} />
      <PageHeader title={t("editPlan")} />
      <ProjectById id={plan.project_id}>{(p) => <PlanForm project={p} plan={plan} />}</ProjectById>
    </div>
  );
}
