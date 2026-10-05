import { initRequestLocale } from "@/i18n/server";
import { UserEdit } from "@/components/users/user-edit";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <UserEdit userId={p.id} />;
}
