import { redirect } from "next/navigation";

// Next 15 makes searchParams a promise in server components, so this awaits
// what it used to read directly. The redirect is otherwise unchanged.
export default async function ExecutionRedirect({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (typeof value === "string") {
      query.set(key, value);
    } else if (Array.isArray(value)) {
      value.forEach((v) => query.append(key, v));
    }
  }
  const qs = query.toString();
  redirect(`/execution/dashboard${qs ? `?${qs}` : ""}`);
}
