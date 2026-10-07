import { initRequestLocale } from "@/i18n/server";
import { PassApplicationEditPage } from "@/components/access/passes";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <PassApplicationEditPage id={p.id} />;
}
