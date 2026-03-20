# Gemini API Proxy Solution for China Mainland Access

## Background

Google Gemini API (`generativelanguage.googleapis.com`) is blocked by GFW in China.
Direct connections result in DNS pollution, SNI blocking, and `503 failed to connect` timeouts.

This document describes a complete, production-tested solution to access Gemini API
from China using a transparent reverse proxy deployed on a free serverless platform.

## Architecture

```
┌──────────────────┐      HTTPS       ┌──────────────────────┐      HTTPS       ┌───────────────────────────────────┐
│  Your Application│ ─────────────── ▶│  Proxy (Netlify /    │ ─────────────── ▶│  generativelanguage.googleapis.com│
│  (China)         │                  │  Cloudflare Worker)  │                  │  (Google Gemini API)              │
└──────────────────┘                  └──────────────────────┘                  └───────────────────────────────────┘
         │                                     │
         │  GEMINI_API_BASE env var            │  Transparent: rewrites Host header,
         │  points SDK to proxy                │  preserves path / query / body / auth
         │                                     │
```

## Platform Selection

| Platform | Domain | China Accessible | Free Tier | Recommended |
|----------|--------|:----------------:|-----------|:-----------:|
| **Netlify Edge Functions** | `*.netlify.app` | Yes | 100GB/month bandwidth | **Yes** |
| Deno Deploy | `*.deno.dev` | Yes | 100K req/day | Yes |
| Cloudflare Workers | `*.workers.dev` | **No (blocked)** | 100K req/day | Only with custom domain |
| Vercel | `*.vercel.app` | **No (blocked)** | 100GB/month | Only with custom domain |

> **Key finding**: `*.workers.dev` and `*.vercel.app` are blocked by GFW (DNS pollution + SNI reset).
> `*.netlify.app` and `*.deno.dev` are currently accessible from China mainland.

---

## Option A: Netlify Edge Functions (Recommended)

### Step 1: Create Project Structure

```
netlify-gemini-proxy/
├── netlify.toml
├── index.html
└── netlify/
    └── edge-functions/
        └── proxy.ts
```

### Step 2: `netlify.toml`

```toml
[[edge_functions]]
  function = "proxy"
  path = "/*"
```

### Step 3: `index.html`

```html
<!DOCTYPE html>
<html><body><p>Gemini API Proxy</p></body></html>
```

### Step 4: `netlify/edge-functions/proxy.ts`

```typescript
const TARGET_HOST = "generativelanguage.googleapis.com";

export default async function handler(request: Request) {
  // Handle CORS preflight
  if (request.method === "OPTIONS") {
    return new Response(null, {
      status: 204,
      headers: {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, PATCH, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, x-goog-api-key",
        "Access-Control-Max-Age": "86400",
      },
    });
  }

  try {
    const url = new URL(request.url);
    url.hostname = TARGET_HOST;
    url.protocol = "https:";
    url.port = "";

    const headers = new Headers(request.headers);
    headers.set("Host", TARGET_HOST);

    const proxyRequest = new Request(url.toString(), {
      method: request.method,
      headers: headers,
      body: request.body,
    });

    const response = await fetch(proxyRequest);

    const responseHeaders = new Headers(response.headers);
    responseHeaders.set("Access-Control-Allow-Origin", "*");

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  } catch (err) {
    return new Response(
      JSON.stringify({ error: "Proxy error", detail: (err as Error).message }),
      {
        status: 502,
        headers: { "Content-Type": "application/json" },
      }
    );
  }
}

export const config = { path: "/*" };
```

### Step 5: Deploy

**Via API (no CLI required):**

```bash
# 1. Get a Personal Access Token from:
#    https://app.netlify.com/user/applications#personal-access-tokens

NETLIFY_TOKEN="nfp_your_token_here"

# 2. Create site
curl -s -X POST "https://api.netlify.com/api/v1/sites" \
  -H "Authorization: Bearer $NETLIFY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"gemini-proxy-yourproject"}'
# Note the site_id from response

# 3. Deploy (using netlify-cli)
npm install -g netlify-cli
NETLIFY_AUTH_TOKEN=$NETLIFY_TOKEN NETLIFY_SITE_ID=<site_id> \
  ntl deploy --prod --dir=.
```

**Via Web UI:**
1. Push the project to a GitHub repo
2. Go to https://app.netlify.com → Import an existing project
3. Connect to the repo and deploy

**Result URL:** `https://gemini-proxy-yourproject.netlify.app`

### Step 6: Verify

```bash
# Should return a Google API error about invalid key (proves proxy works)
curl -s "https://gemini-proxy-yourproject.netlify.app/v1beta/models?key=test"

# Expected response:
# {"error":{"code":400,"message":"API key not valid..."}}
```

---

## Option B: Cloudflare Workers (Requires Custom Domain)

> Only use this if you have your own domain. The default `*.workers.dev` domain is blocked in China.

### Worker Script

```javascript
const TARGET_HOST = "generativelanguage.googleapis.com";

export default {
  async fetch(request) {
    if (!["GET", "POST", "PUT", "DELETE", "PATCH"].includes(request.method)) {
      return new Response("Method Not Allowed", { status: 405 });
    }

    try {
      const url = new URL(request.url);
      url.hostname = TARGET_HOST;
      url.protocol = "https:";

      const headers = new Headers(request.headers);
      headers.set("Host", TARGET_HOST);
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

      const responseHeaders = new Headers(response.headers);
      responseHeaders.set("Access-Control-Allow-Origin", "*");

      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers: responseHeaders,
      });
    } catch (err) {
      return new Response(
        JSON.stringify({ error: "Proxy error", detail: err.message }),
        { status: 502, headers: { "Content-Type": "application/json" } }
      );
    }
  },
};
```

### Custom Domain Setup

1. Deploy the Worker at `dash.cloudflare.com` → Workers & Pages
2. Go to Worker Settings → Triggers → Custom Domains
3. Add `gemini.yourdomain.com` (domain must be on Cloudflare DNS)
4. Use `https://gemini.yourdomain.com` as your `GEMINI_API_BASE`

---

## Python Client Integration

### Dependencies

```
google-generativeai>=0.8.0
google-api-core
```

### Configuration (Environment Variable)

```bash
# .env
GEMINI_API_KEY=AIzaSy...your_key_here
GEMINI_API_BASE=https://gemini-proxy-yourproject.netlify.app
```

### Code: SDK Initialization

The `google-generativeai` SDK supports custom endpoints via `client_options` and `transport` parameters:

```python
import google.generativeai as genai
import os

api_key = os.getenv("GEMINI_API_KEY")
api_base = os.getenv("GEMINI_API_BASE")  # Optional proxy URL

configure_kwargs = {"api_key": api_key}

if api_base:
    from google.api_core import client_options as client_options_lib
    configure_kwargs["transport"] = "rest"
    configure_kwargs["client_options"] = client_options_lib.ClientOptions(
        api_endpoint=api_base
    )

genai.configure(**configure_kwargs)

# Use as normal
model = genai.GenerativeModel("gemini-2.5-flash")
response = model.generate_content("Hello, world!")
print(response.text)
```

**Key parameters explained:**

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `api_key` | Your Gemini API key | Authentication (passed as query param by SDK) |
| `transport` | `"rest"` | Forces HTTP/REST instead of gRPC (required for proxy) |
| `client_options.api_endpoint` | Proxy URL | Redirects all SDK requests to proxy |

> **Important**: `transport="rest"` is mandatory. The default gRPC transport does not
> support custom endpoints cleanly. REST transport works identically for all Gemini API
> features (generateContent, countTokens, listModels, etc.).

### Code: Backward Compatibility Pattern

To support both direct access and proxy access with a single codebase:

```python
import os
import google.generativeai as genai

def configure_gemini():
    """Configure Gemini SDK with optional proxy support."""
    api_key = os.getenv("GEMINI_API_KEY")
    api_base = os.getenv("GEMINI_API_BASE")

    if not api_key:
        raise ValueError("GEMINI_API_KEY is required")

    configure_kwargs = {"api_key": api_key}

    if api_base:
        from google.api_core import client_options as client_options_lib
        configure_kwargs["transport"] = "rest"
        configure_kwargs["client_options"] = client_options_lib.ClientOptions(
            api_endpoint=api_base
        )
        print(f"Using custom Gemini API endpoint: {api_base}")
    else:
        print("Using official Gemini API endpoint")

    genai.configure(**configure_kwargs)
```

When `GEMINI_API_BASE` is not set, the SDK uses the default Google endpoint directly.
No code changes needed to switch between proxy and direct access.

---

## Troubleshooting

### Symptom: `503 failed to connect to all addresses`

**Cause**: Direct connection to Google API blocked by GFW.
**Fix**: Set `GEMINI_API_BASE` to your proxy URL.

### Symptom: `429` / `Max retries exceeded` / `ConnectTimeoutError`

**Cause**: Proxy domain itself is blocked (e.g., `*.workers.dev`).
**Diagnosis**:
```python
import socket
# Check if DNS resolves to a polluted IP
ip = socket.gethostbyname("your-proxy.workers.dev")
print(ip)  # If IP is NOT a Cloudflare IP (104.x.x.x), DNS is polluted

# Check TCP connectivity
s = socket.create_connection((ip, 443), timeout=5)
# TimeoutError = blocked
```
**Fix**: Switch to an accessible platform (Netlify, Deno Deploy) or use a custom domain.

### Symptom: `API key not valid`

**Cause**: API key is wrong or not enabled for Gemini API.
**Fix**: Verify key at https://aistudio.google.com/apikey

### Symptom: Edge function returns HTML instead of JSON

**Cause**: Edge function not deployed or path routing misconfigured.
**Fix**: Verify `netlify.toml` has `path = "/*"` and redeploy.

---

## Quick Verification Checklist

```bash
# 1. Proxy is reachable
curl -s "https://your-proxy.netlify.app/v1beta/models?key=test" | head -5
# Expected: {"error":{"code":400,"message":"API key not valid..."}}

# 2. Proxy forwards correctly with real key
curl -s "https://your-proxy.netlify.app/v1beta/models?key=YOUR_REAL_KEY" | head -5
# Expected: {"models":[{"name":"models/gemini-1.0-pro",...}]}

# 3. Python SDK works through proxy
GEMINI_API_KEY=YOUR_KEY GEMINI_API_BASE=https://your-proxy.netlify.app \
  python -c "
import google.generativeai as genai
from google.api_core import client_options as co
import os
genai.configure(
    api_key=os.environ['GEMINI_API_KEY'],
    transport='rest',
    client_options=co.ClientOptions(api_endpoint=os.environ['GEMINI_API_BASE'])
)
m = genai.GenerativeModel('gemini-2.5-flash')
r = m.generate_content('Say hello in one word')
print('SUCCESS:', r.text)
"
```

---

## Production Notes

- **Latency**: Proxy adds ~200-500ms per request (Netlify edge location → Google).
- **Free tier limits**: Netlify allows 100GB bandwidth/month; a typical Gemini API
  request+response is ~10-50KB, so roughly 2-10 million requests/month.
- **Security**: API keys travel through the proxy. Use HTTPS only. For extra security,
  restrict the proxy to your IP range or add an auth header check in the edge function.
- **Monitoring**: Check Netlify dashboard → Edge Function logs for errors.
- **Fallback**: Consider configuring an OpenAI-compatible API (e.g., DeepSeek, Qwen)
  as a secondary model in case of proxy or Gemini API outages.
