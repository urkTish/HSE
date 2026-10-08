import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { BanListPage } from "@/components/cert/bans";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <BanListPage />;
}
