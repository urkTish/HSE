import { initRequestLocale } from "@/i18n/server";
import { CaDetail } from "@/components/actions/corrective-actions";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <CaDetail id={p.id} />;
}
