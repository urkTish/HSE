import { initRequestLocale } from "@/i18n/server";
import { AvpStickerPrint } from "@/components/access/vehicles";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <AvpStickerPrint id={p.id} />;
}
