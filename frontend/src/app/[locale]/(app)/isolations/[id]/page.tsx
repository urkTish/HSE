import { initRequestLocale } from "@/i18n/server";
import { IsolationDetail } from "@/components/ptw/isolations";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <IsolationDetail id={p.id} />;
}
