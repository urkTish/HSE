import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { UserList } from "@/components/users/user-list";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <UserList />;
}
