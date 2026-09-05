// Función serverless de Vercel. Es la única pieza que conoce la
// SUPABASE_SERVICE_KEY (nunca llega al navegador) y exige un token de
// acceso simple para que la URL no quede abierta a cualquiera.
//
// Variables de entorno a configurar en Vercel:
//   SUPABASE_URL
//   SUPABASE_SERVICE_KEY
//   ACCESS_TOKEN        (invéntate una cadena larga, ej. con `openssl rand -hex 24`)

module.exports = async (req, res) => {
  const { token, days = "90" } = req.query;

  if (!process.env.ACCESS_TOKEN || token !== process.env.ACCESS_TOKEN) {
    res.status(401).json({ error: "unauthorized" });
    return;
  }

  const daysNum = Math.min(Math.max(parseInt(days, 10) || 90, 1), 365);
  const since = new Date(Date.now() - daysNum * 86400000).toISOString().slice(0, 10);

  const base = process.env.SUPABASE_URL.replace(/\/$/, "");
  const headers = {
    apikey: process.env.SUPABASE_SERVICE_KEY,
    Authorization: `Bearer ${process.env.SUPABASE_SERVICE_KEY}`,
  };

  try {
    const [dailyResp, activitiesResp] = await Promise.all([
      fetch(
        `${base}/rest/v1/daily_summary?date=gte.${since}&order=date.asc`,
        { headers }
      ),
      fetch(
        `${base}/rest/v1/activities?start_time=gte.${since}&order=start_time.desc&limit=200`,
        { headers }
      ),
    ]);

    if (!dailyResp.ok || !activitiesResp.ok) {
      const detail = await (dailyResp.ok ? activitiesResp : dailyResp).text();
      res.status(502).json({ error: "supabase_error", detail });
      return;
    }

    const daily = await dailyResp.json();
    const activities = await activitiesResp.json();

    res.setHeader("Cache-Control", "no-store");
    res.status(200).json({ daily, activities });
  } catch (err) {
    res.status(500).json({ error: "server_error", detail: String(err) });
  }
};
