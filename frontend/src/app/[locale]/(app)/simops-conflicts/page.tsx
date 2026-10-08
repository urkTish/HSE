import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { ConflictListPage } from "@/components/ptw/simops";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <ConflictListPage />;
}
