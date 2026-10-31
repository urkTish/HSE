import { initRequestLocale } from "@/i18n/server";
import { WeldDetailPage } from "@/components/quality/q2/welding";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <WeldDetailPage id={p.id} />;
}
