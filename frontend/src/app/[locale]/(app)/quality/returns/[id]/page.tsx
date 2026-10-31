import { initRequestLocale } from "@/i18n/server";
import { ReturnDetailPage } from "@/components/quality/q3/returns";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <ReturnDetailPage id={p.id} />;
}
