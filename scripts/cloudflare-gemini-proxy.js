/**
 * Cloudflare Worker - Gemini API Transparent Reverse Proxy
 *
 * Forwards requests to Google Gemini API (generativelanguage.googleapis.com).
 * Useful for environments where direct access to Google APIs is restricted.
 *
 * Deployment:
 *   1. Log in to https://dash.cloudflare.com → Workers & Pages → Create Worker
 *   2. Paste this script and deploy
 *   3. Note the Worker URL (e.g. https://gemini-proxy.your-account.workers.dev)
 *   4. Set GEMINI_API_BASE=https://gemini-proxy.your-account.workers.dev in .env
 *
 * Free tier: 100,000 requests/day — more than enough for stock analysis.
 */

const TARGET_HOST = "generativelanguage.googleapis.com";

export default {
  async fetch(request) {
    // Only allow expected HTTP methods
    if (!["GET", "POST", "PUT", "DELETE", "PATCH"].includes(request.method)) {
      return new Response("Method Not Allowed", { status: 405 });
    }

    try {
      const url = new URL(request.url);
      url.hostname = TARGET_HOST;
      url.protocol = "https:";

      // Clone headers, override Host
      const headers = new Headers(request.headers);
      headers.set("Host", TARGET_HOST);
      // Remove Cloudflare-specific headers
      headers.delete("cf-connecting-ip");
      headers.delete("cf-ipcountry");
      headers.delete("cf-ray");
      headers.delete("cf-visitor");

      const proxyRequest = new Request(url.toString(), {
        method: request.method,
        headers: headers,
        body: request.body,
        redirect: "follow",
      });

      const response = await fetch(proxyRequest);

      // Return proxied response with CORS headers for flexibility
      const responseHeaders = new Headers(response.headers);
      responseHeaders.set("Access-Control-Allow-Origin", "*");

      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers: responseHeaders,
      });
    } catch (err) {
      return new Response(JSON.stringify({ error: "Proxy error", detail: err.message }), {
        status: 502,
        headers: { "Content-Type": "application/json" },
      });
    }
  },
};
