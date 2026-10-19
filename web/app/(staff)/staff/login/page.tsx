"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useId, useState } from "react";
import { api, setToken } from "@/lib/api";

type StaffOption = { id: string; display_name: string; roles: string[] };
type DevToken = { access_token: string };

export default function DevLogin() {
  const t = useTranslations("staff");
  const tr = useTranslations("roles");
  const router = useRouter();
  const userFieldId = useId();
  const roleFieldId = useId();
  const [staff, setStaff] = useState<StaffOption[] | null>(null);
  const [userId, setUserId] = useState("");
  const [role, setRole] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<StaffOption[]>("/dev/staff")
      .then((list) => {
        setStaff(list);
        if (list[0]) {
          setUserId(list[0].id);
          setRole(list[0].roles[0] ?? "");
        }
      })
      .catch(() => setError(t("loadError")));
  }, [t]);

  const selected = staff?.find((s) => s.id === userId);

  async function signIn(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const res = await api<DevToken>("/dev/login", {
        method: "POST",
        body: JSON.stringify({ user_id: userId, role }),
      });
      setToken(res.access_token);
      router.push("/staff");
    } catch {
      setError(t("loginError"));
    }
  }

  return (
    <main className="mx-auto max-w-md px-4 py-12">
      <h1 className="text-2xl font-bold">{t("loginHeading")}</h1>
      <p role="note" className="mt-4 rounded-md bg-warn-bg p-3 text-sm text-warn-ink">
        {t("demoWarning")}
      </p>
      {error && (
        <p role="alert" className="mt-4 text-red-700">
          {error}
        </p>
      )}
      {!staff && !error && <p className="mt-6">{t("loading")}</p>}
      {staff && (
        <form onSubmit={signIn} className="mt-6 grid gap-4">
          <label htmlFor={userFieldId} className="grid gap-1">
            <span className="font-medium">{t("pickUser")}</span>
            <select
              id={userFieldId}
              value={userId}
              onChange={(e) => {
                setUserId(e.target.value);
                setRole(staff.find((s) => s.id === e.target.value)?.roles[0] ?? "");
              }}
              className="rounded-md border border-line p-2"
            >
              {staff.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.display_name}
                </option>
              ))}
            </select>
          </label>
          <label htmlFor={roleFieldId} className="grid gap-1">
            <span className="font-medium">{t("pickRole")}</span>
            <select
              id={roleFieldId}
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="rounded-md border border-line p-2"
            >
              {selected?.roles.map((r) => (
                <option key={r} value={r}>
                  {tr(r)}
                </option>
              ))}
            </select>
          </label>
          <button
            type="submit"
            disabled={!userId || !role}
            className="rounded-md bg-brand px-4 py-2 font-medium text-brand-ink disabled:opacity-50"
          >
            {t("signIn")}
          </button>
        </form>
      )}
    </main>
  );
}
