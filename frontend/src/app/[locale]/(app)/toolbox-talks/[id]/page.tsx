import { initRequestLocale } from "@/i18n/server";
import { ToolboxTalkPage } from "@/components/field/talks";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <ToolboxTalkPage id={p.id} />;
}
