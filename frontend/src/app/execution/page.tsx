import { redirect } from "next/navigation";

export default function ExecutionRedirect({
  searchParams,
}: {
  searchParams: Record<string, string | string[] | undefined>;
}) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(searchParams)) {
    if (typeof value === "string") {
      query.set(key, value);
    } else if (Array.isArray(value)) {
      value.forEach((v) => query.append(key, v));
    }
  }
  const qs = query.toString();
  redirect(`/execution/dashboard${qs ? `?${qs}` : ""}`);
}
