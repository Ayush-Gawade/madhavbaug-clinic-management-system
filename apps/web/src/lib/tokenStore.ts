/** Access/refresh token persistence.

 * Tokens are kept in localStorage for simplicity of this internal tool. The
 * refresh token enables rotation; on any auth failure the store is cleared.
 */

const ACCESS_KEY = "mb.access_token";
const REFRESH_KEY = "mb.refresh_token";

export const tokenStore = {
  getAccess(): string | null {
    return localStorage.getItem(ACCESS_KEY);
  },
  getRefresh(): string | null {
    return localStorage.getItem(REFRESH_KEY);
  },
  set(accessToken: string, refreshToken: string): void {
    localStorage.setItem(ACCESS_KEY, accessToken);
    localStorage.setItem(REFRESH_KEY, refreshToken);
  },
  clear(): void {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};
