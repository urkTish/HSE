import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { EquipmentListPage } from "@/components/cert/equipment";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <EquipmentListPage />;
}
