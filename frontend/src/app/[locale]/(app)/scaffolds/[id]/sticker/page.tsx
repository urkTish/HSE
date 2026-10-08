import { initRequestLocale } from "@/i18n/server";
import { ScaffoldStickerPage } from "@/components/cert/scaffolds";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <ScaffoldStickerPage id={p.id} />;
}
