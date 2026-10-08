import { initRequestLocale } from "@/i18n/server";
import { SessionDetail } from "@/components/training/sessions";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <SessionDetail id={decodeURIComponent(p.id)} />;
}
