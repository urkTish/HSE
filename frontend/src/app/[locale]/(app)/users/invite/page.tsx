import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { UserInvite } from "@/components/users/user-invite";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <UserInvite />;
}
