const { Buffer } = require("node:buffer");

function getBackendBaseUrl() {
  const raw = process.env.RENDER_BACKEND_URL || "https://trafficdetect-vehicledetection-counting.onrender.com";
  return raw.endsWith("/") ? raw.slice(0, -1) : raw;
}

function copyHeaders(sourceHeaders) {
  const headers = new Headers();
  for (const [key, value] of Object.entries(sourceHeaders)) {
    const lower = key.toLowerCase();
    if (lower === "host" || lower === "content-length" || lower === "connection") {
      continue;
    }
    headers.set(key, value);
  }
  return headers;
}

async function readRequestBody(req) {
  if (req.method === "GET" || req.method === "HEAD") {
    return undefined;
  }

  const chunks = [];
  for await (const chunk of req) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  }

  if (chunks.length === 0) {
    return undefined;
  }

  return Buffer.concat(chunks);
}

async function proxyRequest(req, res, targetPath) {
  try {
    const backendUrl = new URL(targetPath, getBackendBaseUrl());
    const headers = copyHeaders(req.headers);
    const body = await readRequestBody(req);

    const response = await fetch(backendUrl, {
      method: req.method,
      headers,
      body,
      redirect: "manual",
    });

    res.statusCode = response.status;

    response.headers.forEach((value, key) => {
      const lower = key.toLowerCase();
      if (lower === "content-length" || lower === "transfer-encoding" || lower === "connection") {
        return;
      }
      res.setHeader(key, value);
    });

    if (!response.body) {
      res.end();
      return;
    }

    const reader = response.body.getReader();
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      res.write(Buffer.from(value));
    }
    res.end();
  } catch (error) {
    res.statusCode = 500;
    res.setHeader("content-type", "application/json");
    res.end(JSON.stringify({ error: error instanceof Error ? error.message : "Proxy request failed" }));
  }
}

module.exports = { proxyRequest };
