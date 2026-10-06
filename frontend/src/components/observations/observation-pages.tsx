"use client";
import { useTranslations } from "next-intl";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { PageHeader } from "@/components/common/page-header";
import { ProjectById, ProjectGate } from "@/components/common/project-gate";
import { ErrorState, LoadingState } from "@/components/common/states";
import { ObservationForm, ObservationList } from "@/components/observations/observations";
import { useObservation } from "@/lib/api/hse";

export function ObservationListPage() {
  return <ProjectGate>{(p) => <ObservationList project={p} />}</ProjectGate>;
}

export function ObservationCreatePage() {
  const t = useTranslations("observations");
  const tn = useTranslations("nav");
  return (
    <div>
      <Breadcrumbs items={[{ label: tn("observations"), href: "/observations" }, { label: t("createTitle") }]} />
      <PageHeader title={t("createTitle")} />
      <ProjectGate>{(p) => <ObservationForm project={p} />}</ProjectGate>
    </div>
  );
}

export function ObservationEditPage({ id }: { id: string }) {
  const t = useTranslations("observations");
  const tn = useTranslations("nav");
  const q = useObservation(id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const o = q.data;
  return (
    <div>
      <Breadcrumbs items={[{ label: tn("observations"), href: "/observations" }, { label: o.ref, href: `/observations/${o.id}` }, { label: t("editTitle") }]} />
      <PageHeader title={t("editTitle")} />
      <ProjectById id={o.project_id}>{(p) => <ObservationForm project={p} obs={o} />}</ProjectById>
    </div>
  );
}
