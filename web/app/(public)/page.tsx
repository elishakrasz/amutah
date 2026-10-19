import { getTranslations } from "next-intl/server";

export default async function Home() {
  const t = await getTranslations("home");
  const actions = [t("apply"), t("refer"), t("status")];
  return (
    <main className="mx-auto max-w-2xl px-4 py-12">
      <h1 className="text-3xl font-bold">{t("heading")}</h1>
      <p className="mt-4 text-lg leading-relaxed">{t("intro")}</p>
      <ul className="mt-8 grid gap-3 sm:grid-cols-3">
        {actions.map((label) => (
          <li
            key={label}
            className="rounded-lg border border-line p-4 text-center text-muted"
          >
            <span className="block font-medium text-ink">{label}</span>
            <span className="text-sm">{t("comingSoon")}</span>
          </li>
        ))}
      </ul>
    </main>
  );
}
