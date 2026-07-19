/**
 * Resolve the Electron-managed FastAPI configuration.
 *
 * The desktop app owns a local backend only. Its bind host is fixed to
 * loopback; `ELECTION_API_BASE_URL` changes the client target, never the host
 * of a spawned child process.
 */

export const ELECTRON_FASTAPI_LOOPBACK_HOST = "127.0.0.1";

export function resolveElectronFastApiRuntimeConfig(env = process.env) {
  const port = Number(env.ELECTION_API_PORT ?? "8000");
  const externalBaseUrl = env.ELECTION_API_BASE_URL;

  return {
    host: ELECTRON_FASTAPI_LOOPBACK_HOST,
    port,
    baseUrl:
      externalBaseUrl ?? `http://${ELECTRON_FASTAPI_LOOPBACK_HOST}:${port}`,
    hasExternalBaseUrl: Boolean(externalBaseUrl),
  };
}
