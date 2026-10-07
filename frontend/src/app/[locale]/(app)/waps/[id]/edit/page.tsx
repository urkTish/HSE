import { initRequestLocale } from "@/i18n/server";
import { WapEditPage } from "@/components/access/waps";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <WapEditPage id={p.id} />;
}
