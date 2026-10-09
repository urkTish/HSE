import { initRequestLocale } from "@/i18n/server";
import { TemplatePage } from "@/components/field/library";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <TemplatePage id={p.id} />;
}
