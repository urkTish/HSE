import { initRequestLocale } from "@/i18n/server";
import { ContractorDetail } from "@/components/contractors/contractor-detail";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <ContractorDetail contractorId={p.id} />;
}
