import { initRequestLocale } from "@/i18n/server";
import { MusterPage } from "@/components/emergency/muster";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <MusterPage id={p.id} />;
}
