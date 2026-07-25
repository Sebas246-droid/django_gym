# Despliegue en Railway

GymPilot corre en Railway con PostgreSQL administrado y las fotos en un bucket
S3. Los estaticos los sirve el propio Django con WhiteNoise; no necesitan bucket.

## Que hace cada archivo

| Archivo | Para que sirve |
|---|---|
| `Procfile` | Comandos de `release` (migraciones + datos base) y `web` (gunicorn). |
| `railway.json` | Build (collectstatic), pre-deploy, healthcheck y reinicios. |
| `.python-version` | Fija Python 3.12 en el build. |
| `requirements.txt` | Dependencias, incluidas las de produccion. |

En el arranque (`release` / `preDeployCommand`) se corre, en orden:

1. `migrate` — crea/actualiza las tablas.
2. `init_saas` — roles (Groups) y planes base. Idempotente.
3. `crear_superusuario` — el super admin, desde variables de entorno.

## Paso a paso

### 1. Proyecto y base de datos

1. En Railway: **New Project → Deploy from GitHub repo** (sube antes este repo a GitHub).
2. **New → Database → PostgreSQL**. Railway crea `DATABASE_URL` y la comparte
   con el servicio web automaticamente.

### 2. Bucket S3 para las fotos

Sirve cualquier S3 o compatible (AWS S3, Cloudflare R2, MinIO). En AWS:

1. Crea un bucket, por ejemplo `gympilot-media`, con acceso publico de lectura.
2. Crea un usuario IAM con permeso de escritura sobre ese bucket y genera una
   llave de acceso.

### 3. Variables de entorno del servicio web

En **Variables** del servicio (no en `.env`, eso es solo local):

```
SECRET_KEY=<una llave larga y aleatoria>
DEBUG=False
ALLOWED_HOSTS=            # opcional; RAILWAY_PUBLIC_DOMAIN ya se agrega sola

# Fotos en S3
AWS_STORAGE_BUCKET_NAME=gympilot-media
AWS_ACCESS_KEY_ID=<...>
AWS_SECRET_ACCESS_KEY=<...>
AWS_S3_REGION_NAME=us-east-1
AWS_S3_CUSTOM_DOMAIN=gympilot-media.s3.us-east-1.amazonaws.com

# Super administrador (se crea en el primer deploy)
SUPERUSER_USERNAME=admin
SUPERUSER_EMAIL=tu@correo.com
SUPERUSER_PASSWORD=<una contrasena fuerte>
```

`DATABASE_URL` la inyecta Railway al enlazar PostgreSQL: no la escribas a mano.

Para generar `SECRET_KEY`:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 4. Desplegar

Railway construye e inicia solo al detectar el push. En el primer deploy quedan
las tablas, los roles, los planes y el super administrador. Entra a
`https://<tu-dominio>.up.railway.app/` con el usuario y contrasena del super
admin y da de alta el primer gimnasio.

## Notas

- **Estaticos**: `collectstatic` corre en el build; WhiteNoise los sirve
  comprimidos y con hash. No requieren bucket.
- **Por que las fotos van a S3**: el disco de Railway no sobrevive a un redeploy.
  Sin bucket, las fotos que suban los gimnasios se perderian en cada despliegue.
  Si no defines el bucket, el sistema usa disco local (bien para pruebas).
- **Healthcheck**: Railway consulta `/salud/`, que responde sin tocar la base.
- **SSL**: con `DEBUG=False` se fuerza HTTPS, cookies seguras y HSTS. Railway
  termina el TLS y manda `X-Forwarded-Proto`, que Django ya reconoce.
- **Migraciones nuevas**: se aplican solas en cada deploy por el paso `release`.
