import { initRequestLocale } from "@/i18n/server";
import { TestDetailPage } from "@/components/quality/q2/testing";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <TestDetailPage id={p.id} />;
}
