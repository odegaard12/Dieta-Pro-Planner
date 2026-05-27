# Integraciones

## Strava

La app incluye soporte para conectar Strava con OAuth y sincronizar actividades manualmente, solo cuando el usuario pulse el botón de sincronizar.

Variables locales en `.env`:

```env
STRAVA_CLIENT_ID=
STRAVA_CLIENT_SECRET=
STRAVA_REDIRECT_URI=http://TU_HOST:8099/api/strava/callback
```

Los tokens se guardan en `data/strava_tokens.json` y no se suben al repositorio.

## Zepp / Amazfit

La ruta práctica es sincronizar Zepp con Strava y que Dieta Pro importe desde Strava. No se guarda ninguna credencial de Zepp en esta app.
