(() => {
  const API_BASE = "https://rail-optimax.onrender.com";

  window.RAILOPTIMAX_API_BASE = API_BASE;
  window.RAILOPTIMAX_WS_URL =
    "wss://rail-optimax.onrender.com/ws/live-telemetry";

  const nativeFetch = window.fetch.bind(window);

  const API_PREFIXES = [
    "/ai/",
    "/maintenance/",
    "/blocks",
    "/trains/",
    "/health",
    "/coordination-opportunities",
    "/operator/",
  ];

  window.fetch = (input, init) => {
    let url;

    if (typeof input === "string") {
      url = new URL(input, window.location.href);
    } else if (input instanceof Request) {
      url = new URL(input.url);
    } else {
      return nativeFetch(input, init);
    }

    const isBackendPath =
      url.origin === window.location.origin &&
      API_PREFIXES.some((prefix) => url.pathname.startsWith(prefix));

    if (!isBackendPath) {
      return nativeFetch(input, init);
    }

    const targetUrl = API_BASE + url.pathname + url.search;

    if (input instanceof Request) {
      return nativeFetch(new Request(targetUrl, input), init);
    }

    return nativeFetch(targetUrl, init);
  };
})();
