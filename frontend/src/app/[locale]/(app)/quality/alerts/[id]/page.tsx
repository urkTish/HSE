import { initRequestLocale } from "@/i18n/server";
import { AlertDetailPage } from "@/components/quality/q0/records";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <AlertDetailPage id={p.id} />;
}
