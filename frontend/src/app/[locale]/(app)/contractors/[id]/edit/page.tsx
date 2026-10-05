import { initRequestLocale } from "@/i18n/server";
import { ContractorEdit } from "@/components/contractors/contractor-pages";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <ContractorEdit contractorId={p.id} />;
}
