import { initRequestLocale } from "@/i18n/server";
import { NotamDetail } from "@/components/access/works";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <NotamDetail id={p.id} />;
}
