/** Resolved API base path for Axios and fetch calls. */
export function getApiBasePath(): string {
  const raw = import.meta.env.VITE_API_BASE_URL?.trim();
  if (!raw) {
    return "/api/v1";
  }
  return `${raw.replace(/\/$/, "")}/api/v1`;
}
