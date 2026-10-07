import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { GateCheckScreen } from "@/components/gate/gate-check";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <GateCheckScreen />;
}
