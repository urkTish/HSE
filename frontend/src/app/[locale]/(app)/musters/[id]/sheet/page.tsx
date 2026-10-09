import { initRequestLocale } from "@/i18n/server";
import { MusterSheetPage } from "@/components/emergency/muster";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <MusterSheetPage id={p.id} />;
}
