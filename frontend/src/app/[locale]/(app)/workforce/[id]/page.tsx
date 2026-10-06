import { initRequestLocale } from "@/i18n/server";
import { WorkforceDetail } from "@/components/workforce/workforce-detail";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <WorkforceDetail id={p.id} />;
}
