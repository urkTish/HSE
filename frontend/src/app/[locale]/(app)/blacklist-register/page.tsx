import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { BlacklistRegisterPage } from "@/components/cert/bans";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <BlacklistRegisterPage />;
}
