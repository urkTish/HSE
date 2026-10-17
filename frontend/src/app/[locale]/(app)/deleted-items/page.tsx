import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { DeletedItemsPage } from "@/components/users/deleted-items";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <DeletedItemsPage />;
}
