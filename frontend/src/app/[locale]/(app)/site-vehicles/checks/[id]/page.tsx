import { initRequestLocale } from "@/i18n/server";
import { PreUseCheckDetailPage } from "@/components/site-vehicles/checks";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <PreUseCheckDetailPage id={p.id} />;
}
