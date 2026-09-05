// Chat consultivo, compartido entre index.html y coach.html. Habla con
// /api/chat (que a su vez habla con la API de Claude usando tu
// ANTHROPIC_API_KEY, guardada solo en Vercel). Puede llamar herramientas de
// la propia página (los slots) — el ciclo de "Claude pide una herramienta →
// la página la ejecuta → se le regresa el resultado" corre aquí mismo.
//
// Uso:
//   initChat({
//     token, formId, inputId, messagesId, hintId,
//     systemPrompt: "...", buildContext: () => "...",
//     tools: [{ name, description, inputSchema, execute(input) {...} }],
//   });

function initChat({ token, formId, inputId, messagesId, hintId, systemPrompt, buildContext, tools }) {
  const form = document.getElementById(formId);
  const input = document.getElementById(inputId);
  const messagesEl = document.getElementById(messagesId);
  const hintEl = document.getElementById(hintId);
  let history = [];
  let busy = false;

  if (!token) {
    hintEl.textContent = "Falta el token de acceso.";
    input.disabled = true;
    form.querySelector("button").disabled = true;
    return;
  }

  function setDisabled(v) {
    input.disabled = v;
    form.querySelector("button").disabled = v;
  }

  function addBubble(role, text) {
    const div = document.createElement("div");
    div.className = "chat-msg " + role;
    div.textContent = text;
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return div;
  }

  async function callBackend(messages) {
    const resp = await fetch(`/api/chat?token=${encodeURIComponent(token)}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        system: systemPrompt + "\n\nDATOS ACTUALES:\n" + buildContext(),
        messages,
        tools: (tools || []).map((t) => ({ name: t.name, description: t.description, inputSchema: t.inputSchema })),
      }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      const err = new Error(data?.error || "chat_error");
      err.status = resp.status;
      err.code = data?.error;
      throw err;
    }
    return data;
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (busy) return;
    const msg = input.value.trim();
    if (!msg) return;
    input.value = "";
    addBubble("user", msg);
    const bubble = addBubble("assistant", "Pensando…");
    busy = true; setDisabled(true);

    let working = [...history, { role: "user", content: msg }];
    let finalText = "";
    try {
      for (let round = 0; round < 4; round++) {
        const data = await callBackend(working);
        working.push({ role: "assistant", content: data.content });
        const toolUses = (data.content || []).filter((b) => b.type === "tool_use");
        const text = (data.content || []).filter((b) => b.type === "text").map((b) => b.text).join("\n");
        if (text) { finalText = text; bubble.textContent = finalText; }
        if (data.stop_reason !== "tool_use" || !toolUses.length) break;
        const toolResults = toolUses.map((tu) => {
          const toolDef = (tools || []).find((t) => t.name === tu.name);
          let result;
          try { result = toolDef ? toolDef.execute(tu.input) : "Herramienta no encontrada."; }
          catch (err) { result = "Error: " + err.message; }
          return { type: "tool_result", tool_use_id: tu.id, content: String(result) };
        });
        working.push({ role: "user", content: toolResults });
      }
      history = working.slice(-20);
      if (!finalText) bubble.textContent = "No pude responder eso, intenta con otra pregunta.";
    } catch (err) {
      const copy = {
        missing_api_key: "El chat todavía no está configurado (falta ANTHROPIC_API_KEY en Vercel).",
        unauthorized: "Token inválido.",
        anthropic_error: "Hubo un problema con el chat, intenta de nuevo en un momento.",
      }[err.code] || "Hubo un problema, intenta de nuevo.";
      bubble.textContent = copy;
    } finally {
      busy = false; setDisabled(false);
    }
  });
}
