import { Suspense } from "react";
import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { AcceptInvite } from "@/components/auth/accept-invite";

export default async function AcceptInvitePage({ params }: LocaleParams) {
  await initRequestLocale(params);
  return (
    <Suspense>
      <AcceptInvite />
    </Suspense>
  );
}
