import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { IsolationCreatePage } from "@/components/ptw/isolations";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <IsolationCreatePage />;
}
