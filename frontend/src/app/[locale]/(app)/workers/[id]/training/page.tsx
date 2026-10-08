import { initRequestLocale } from "@/i18n/server";
import { TrainingPassportPage } from "@/components/training/passport";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <TrainingPassportPage id={decodeURIComponent(p.id)} />;
}
