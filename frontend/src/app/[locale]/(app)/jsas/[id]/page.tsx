import { initRequestLocale } from "@/i18n/server";
import { JsaDetail } from "@/components/ptw/jsa";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <JsaDetail id={p.id} />;
}
