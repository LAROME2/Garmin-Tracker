# Mi Garmin — histórico + webapp

Toma tus datos de Garmin Connect todos los días, los guarda en una base de
datos propia (así acumulas historial más allá de lo que Garmin retiene) y te
los muestra en una webapp que puedes agregar a la pantalla de inicio de tu
celular.

No usa el servidor MCP `garmin_mcp` directamente (ese es para preguntarle a
Claude cosas puntuales en el chat), pero reutiliza la misma librería
(`garminconnect`) para autenticarse.

## Piezas

- `collector/fetch_garmin.py` — se conecta a Garmin y guarda tus datos en Supabase. Corre en GitHub Actions, gratis.
- `supabase/schema.sql` — las tablas donde vive el historial.
- `webapp/` — la página que ves (gráficas) + una función que sirve los datos. Se despliega en Vercel, gratis.

Todo el stack es de capa gratuita. No necesitas dejar tu computadora prendida.

## 1. Crear la base de datos (Supabase)

1. Crea una cuenta/proyecto en [supabase.com](https://supabase.com) (plan gratis).
2. Ve a **SQL Editor** → pega el contenido de `supabase/schema.sql` → Run.
3. Ve a **Settings → API** y copia:
   - `Project URL` → esto es `SUPABASE_URL`
   - `service_role` key (⚠️ no la `anon` key) → esto es `SUPABASE_SERVICE_KEY`

## 2. Generar tus tokens de Garmin

Si ya configuraste `garmin_mcp` con Claude Desktop, ya corriste `garmin-mcp-auth`
y tienes tokens guardados en `~/.garminconnect`. Si no:

```bash
uvx --python 3.12 --from git+https://github.com/Taxuspt/garmin_mcp garmin-mcp-auth
```

(te pedirá email, password y el código MFA si tienes activada verificación en dos pasos).

Ahora empaca esa carpeta en una sola cadena de texto para guardarla como secreto:

```bash
# macOS/Linux — copia el resultado al portapapeles
tar -C ~/.garminconnect -czf - . | base64 | pbcopy
```

(En Windows/WSL usa `base64 -w0` en vez de `pbcopy` y copia el resultado a mano).

Esto es lo que vas a pegar como el secreto `GARMIN_TOKENS_B64` en el paso 4.
Los tokens duran varios meses; cuando expiren, repite este paso.

## 3. Subir este repo a GitHub

Crea un repositorio nuevo (recomendado: **privado**) y sube esta carpeta tal cual.

## 4. Configurar los secretos en GitHub Actions

En el repo: **Settings → Secrets and variables → Actions → New repository secret**.
Crea estos tres:

| Nombre | Valor |
|---|---|
| `GARMIN_TOKENS_B64` | lo que copiaste en el paso 2 |
| `SUPABASE_URL` | del paso 1 |
| `SUPABASE_SERVICE_KEY` | del paso 1 |

## 5. Cargar los primeros 3 meses de historial

El workflow ya está en `.github/workflows/collect.yml` y corre solo una vez al
día. Para la primera carga, dispáralo a mano pidiéndole 90 días:

**Actions → "Recolectar datos de Garmin" → Run workflow** → en
`backfill_days` escribe `90` → Run workflow.

Revisa los logs: si algo del login falla, casi siempre es que el token
expiró o Garmin pidió MFA de nuevo — repite el paso 2.

Después de eso, el workflow corre automático cada día (por defecto trae los
últimos 5 días, así no importa si un día falla).

## 6. Desplegar la webapp (Vercel)

1. En [vercel.com](https://vercel.com), **Add New → Project** → importa el mismo repo.
2. **Root Directory:** `webapp`
3. Framework preset: "Other" (no necesita build).
4. En **Environment Variables** agrega:
   - `SUPABASE_URL` (la misma de antes)
   - `SUPABASE_SERVICE_KEY` (la misma de antes)
   - `ACCESS_TOKEN` — invéntate una cadena larga y difícil de adivinar, por ejemplo corriendo `openssl rand -hex 24` en tu terminal.
5. Deploy.

Al terminar te da una URL tipo `https://mi-garmin-xxxx.vercel.app`.

## 7. Abrirla y agregarla a tu celular

Abre en el navegador del celular:

```
https://mi-garmin-xxxx.vercel.app/?token=EL_ACCESS_TOKEN_QUE_PUSISTE
```

La página guarda el token en el navegador, así que de ahí en adelante no
tienes que volver a escribirlo. Luego:

- **iPhone (Safari):** botón de compartir → "Agregar a pantalla de inicio".
- **Android (Chrome):** menú (⋮) → "Añadir a pantalla de inicio".

Te queda un ícono como cualquier app. Ábrelo cuando quieras, sin depender de
tu computadora — solo necesita internet en el celular.

## Notas de seguridad

- No compartas el link con `?token=...` — quien lo tenga puede ver tus datos.
- La `service_role` key de Supabase nunca sale del backend (GitHub Actions /
  función de Vercel); el navegador solo ve tu `ACCESS_TOKEN` propio, no la de Supabase.
- Repo privado recomendado, aunque ningún secreto queda en el código.

## Ajustar qué se guarda

`collector/fetch_garmin.py` es corto a propósito — agrega ahí más llamadas a
`python-garminconnect` (VO2 max, HRV detallado, peso, etc.) y una columna en
`supabase/schema.sql` si luego quieres más métricas en la webapp.
