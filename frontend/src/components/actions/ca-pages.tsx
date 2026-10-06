"use client";
import { useTranslations } from "next-intl";
import { CaForm, CaList } from "@/components/actions/corrective-actions";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { PageHeader } from "@/components/common/page-header";
import { ProjectById, ProjectGate } from "@/components/common/project-gate";
import { ErrorState, LoadingState } from "@/components/common/states";
import { useCorrectiveAction } from "@/lib/api/hse";

export function CaListPage() {
  return <ProjectGate>{(p) => <CaList project={p} />}</ProjectGate>;
}

export function CaCreatePage() {
  const t = useTranslations("ca");
  const tn = useTranslations("nav");
  return (
    <div>
      <Breadcrumbs items={[{ label: tn("actions"), href: "/actions" }, { label: t("createTitle") }]} />
      <PageHeader title={t("createTitle")} />
      <ProjectGate>{(p) => <CaForm project={p} />}</ProjectGate>
    </div>
  );
}

export function CaEditPage({ id }: { id: string }) {
  const t = useTranslations("ca");
  const tn = useTranslations("nav");
  const q = useCorrectiveAction(id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const c = q.data;
  return (
    <div>
      <Breadcrumbs items={[{ label: tn("actions"), href: "/actions" }, { label: c.ref, href: `/actions/${c.id}` }, { label: t("editTitle") }]} />
      <PageHeader title={t("editTitle")} />
      <ProjectById id={c.project_id}>{(p) => <CaForm project={p} ca={c} />}</ProjectById>
    </div>
  );
}
