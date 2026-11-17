const KEY = "wswe_after_auth";
export function setAfterAuth(path: string) {
  if (path.startsWith("/") && !path.startsWith("//")) localStorage.setItem(KEY, path);
}
export function takeAfterAuth(): string {
  const p = localStorage.getItem(KEY);
  localStorage.removeItem(KEY);
  return p && p.startsWith("/") && !p.startsWith("//") ? p : "/teams";
}
