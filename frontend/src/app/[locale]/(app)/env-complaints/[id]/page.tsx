import { initRequestLocale } from "@/i18n/server";
import { ComplaintPage } from "@/components/env/spills";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <ComplaintPage id={p.id} />;
}
