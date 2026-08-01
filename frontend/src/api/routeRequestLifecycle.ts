const managedPagePaths = new Set([
  "/app/dashboard",
  "/app/report",
  "/app/store",
  "/app/product",
  "/app/inventory",
  "/app/member",
]);

const isManagedPage = (path: string) =>
  managedPagePaths.has(path) || path.startsWith("/app/ai-diagnosis/");

export const shouldScopeRouteRequest = (
  method: string | undefined,
  path: string,
  persistAcrossRoutes: boolean | undefined,
  hasCallerSignal: boolean,
) => {
  if (persistAcrossRoutes || hasCallerSignal || !isManagedPage(path)) return false;
  return ["get", "head"].includes((method || "get").toLowerCase());
};

export const isRouteRequestCanceled = (error: any) =>
  Boolean(
    error?.config?.routeScoped &&
    (error?.code === "ERR_CANCELED" || error?.__CANCEL__ === true),
  );

export class RouteRequestLifecycle {
  private controller = new AbortController();

  get signal() {
    return this.controller.signal;
  }

  cancel() {
    this.controller.abort();
    this.controller = new AbortController();
  }
}
