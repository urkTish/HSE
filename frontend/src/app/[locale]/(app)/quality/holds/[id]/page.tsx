import { initRequestLocale } from "@/i18n/server";
import { HoldDetailPage } from "@/components/quality/q3/holds";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <HoldDetailPage id={p.id} />;
}
