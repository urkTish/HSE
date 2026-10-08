import { initRequestLocale } from "@/i18n/server";
import { DefectDetail } from "@/components/cert/defects";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <DefectDetail id={p.id} />;
}
