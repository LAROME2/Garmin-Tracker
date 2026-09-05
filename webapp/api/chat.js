// Función serverless de Vercel. Es la única pieza que conoce la
// ANTHROPIC_API_KEY (nunca llega al navegador) y exige el mismo token de
// acceso que /api/data. Es un simple proxy a la API de mensajes de Claude —
// la ejecución de herramientas (los slots) pasa aquí y de regreso al
// navegador, pero corre en el navegador porque es ahí donde vive el estado
// de la página.
//
// Variable de entorno nueva a configurar en Vercel:
//   ANTHROPIC_API_KEY   tu API key de https://console.anthropic.com

const MODEL = "claude-3-5-haiku-20241022";

module.exports = async (req, res) => {
  if (req.method !== "POST") {
    res.status(405).json({ error: "method_not_allowed" });
    return;
  }

  const { token } = req.query;
  if (!process.env.ACCESS_TOKEN || token !== process.env.ACCESS_TOKEN) {
    res.status(401).json({ error: "unauthorized" });
    return;
  }
  if (!process.env.ANTHROPIC_API_KEY) {
    res.status(500).json({ error: "missing_api_key" });
    return;
  }

  let body = req.body;
  if (typeof body === "string") {
    try { body = JSON.parse(body); } catch { body = {}; }
  }
  const { system, messages, tools } = body || {};
  if (!Array.isArray(messages) || messages.length === 0) {
    res.status(400).json({ error: "bad_request", detail: "falta messages" });
    return;
  }

  const anthropicTools = Array.isArray(tools) && tools.length
    ? tools.map((t) => ({
        name: t.name,
        description: t.description,
        input_schema: t.inputSchema || { type: "object", properties: {} },
      }))
    : undefined;

  try {
    const resp = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "x-api-key": process.env.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
      },
      body: JSON.stringify({
        model: MODEL,
        max_tokens: 600,
        ...(system ? { system } : {}),
        messages,
        ...(anthropicTools ? { tools: anthropicTools } : {}),
      }),
    });

    const data = await resp.json();
    if (!resp.ok) {
      res.status(resp.status).json({ error: "anthropic_error", detail: data });
      return;
    }
    res.setHeader("Cache-Control", "no-store");
    res.status(200).json(data);
  } catch (err) {
    res.status(500).json({ error: "server_error", detail: String(err) });
  }
};
