import { initRequestLocale } from "@/i18n/server";
import { PunchDetailPage } from "@/components/quality/q1/punch";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <PunchDetailPage id={p.id} />;
}
