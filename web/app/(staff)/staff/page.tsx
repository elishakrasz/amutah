"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { api, setToken } from "@/lib/api";

type WhoAmI = { user_id: string; role: string; display_name: string };

export default function StaffHome() {
  const t = useTranslations("staff");
  const tr = useTranslations("roles");
  const router = useRouter();
  const [me, setMe] = useState<WhoAmI | null | undefined>(undefined);

  useEffect(() => {
    api<WhoAmI>("/whoami")
      .then(setMe)
      .catch(() => setMe(null));
  }, []);

  if (me === undefined) return <main className="p-8">{t("loading")}</main>;
  if (me === null) {
    return (
      <main className="mx-auto max-w-md px-4 py-12">
        <p>{t("notSignedIn")}</p>
        <Link href="/staff/login" className="mt-4 inline-block text-brand underline">
          {t("goToLogin")}
        </Link>
      </main>
    );
  }
  return (
    <main className="mx-auto max-w-2xl px-4 py-12">
      <p className="text-lg">{t("signedInAs", { name: me.display_name, role: tr(me.role) })}</p>
      <button
        type="button"
        onClick={() => {
          setToken(null);
          router.push("/staff/login");
        }}
        className="mt-6 rounded-md border border-line px-4 py-2"
      >
        {t("signOut")}
      </button>
    </main>
  );
}
