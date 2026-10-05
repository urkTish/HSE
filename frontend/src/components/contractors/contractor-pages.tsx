"use client";
import { useTranslations } from "next-intl";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { PageHeader } from "@/components/common/page-header";
import { ErrorState, LoadingState } from "@/components/common/states";
import { ContractorForm } from "@/components/contractors/contractor-form";
import { useContractor } from "@/lib/api/queries";

export function ContractorCreate() {
  const t = useTranslations("contractor");
  const tn = useTranslations("nav");
  return (
    <div>
      <Breadcrumbs items={[{ label: tn("contractors"), href: "/contractors" }, { label: t("createTitle") }]} />
      <PageHeader title={t("createTitle")} />
      <ContractorForm />
    </div>
  );
}

export function ContractorEdit({ contractorId }: { contractorId: string }) {
  const t = useTranslations("contractor");
  const tn = useTranslations("nav");
  const q = useContractor(contractorId);
  if (q.isError) return <ErrorState error={q.error} />;
  if (!q.data) return <LoadingState />;
  return (
    <div>
      <Breadcrumbs
        items={[
          { label: tn("contractors"), href: "/contractors" },
          { label: q.data.short_code, href: `/contractors/${q.data.id}` },
          { label: t("editTitle") },
        ]}
      />
      <PageHeader title={t("editTitle")} />
      <ContractorForm contractor={q.data} />
    </div>
  );
}
