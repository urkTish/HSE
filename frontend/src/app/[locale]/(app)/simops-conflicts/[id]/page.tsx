import { initRequestLocale } from "@/i18n/server";
import { ConflictDetail } from "@/components/ptw/simops";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <ConflictDetail id={p.id} />;
}
