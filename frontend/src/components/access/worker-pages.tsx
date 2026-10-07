"use client";
import { useTranslations } from "next-intl";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { PageHeader } from "@/components/common/page-header";
import { ProjectGate } from "@/components/common/project-gate";
import { ErrorState, LoadingState } from "@/components/common/states";
import { useEffect } from "react";
import { useRouter } from "@/i18n/navigation";
import { useDeployment, useWorker } from "@/lib/api/access";
import { WorkerForm, WorkerList } from "./workers";

export function WorkerListPage() {
  return <ProjectGate>{(p) => <WorkerList project={p} />}</ProjectGate>;
}

export function WorkerCreatePage() {
  const t = useTranslations("workers");
  const tn = useTranslations("nav");
  return (
    <div>
      <Breadcrumbs items={[{ label: tn("workers"), href: "/workers" }, { label: t("new") }]} />
      <PageHeader title={t("new")} />
      <ProjectGate>{(p) => <WorkerForm project={p} />}</ProjectGate>
    </div>
  );
}

export function WorkerEditPage({ id }: { id: string }) {
  const t = useTranslations("workers");
  const tn = useTranslations("nav");
  const q = useWorker(id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const w = q.data;
  return (
    <div>
      <Breadcrumbs items={[{ label: tn("workers"), href: "/workers" }, { label: w.worker_no, href: `/workers/${w.id}` }, { label: t("editTitle") }]} />
      <PageHeader title={t("editTitle")} />
      <ProjectGate>{(p) => <WorkerForm project={p} worker={w} />}</ProjectGate>
    </div>
  );
}

/** Deployments have no page of their own: open the worker with the deployment selected. */
export function DeploymentRedirect({ id }: { id: string }) {
  const q = useDeployment(id);
  const router = useRouter();
  const target = q.data ? `/workers/${q.data.worker_id}?project=${q.data.project_id}` : null;
  useEffect(() => {
    if (target) router.replace(target);
  }, [target, router]);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  return <LoadingState />;
}
