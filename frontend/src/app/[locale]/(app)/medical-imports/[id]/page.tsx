import { initRequestLocale } from "@/i18n/server";
import { MedicalImportDetail } from "@/components/medical/imports";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <MedicalImportDetail id={decodeURIComponent(p.id)} />;
}
