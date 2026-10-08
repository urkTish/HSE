import { initRequestLocale } from "@/i18n/server";
import { TrainingImportDetail } from "@/components/training/imports";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <TrainingImportDetail id={decodeURIComponent(p.id)} />;
}
