"""
Django settings for GymPilot.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-dev-key-change-me')

ON_RAILWAY = bool(os.getenv('RAILWAY_ENVIRONMENT') or os.getenv('RAILWAY_PUBLIC_DOMAIN'))

# En Railway el sitio es de produccion: DEBUG apagado por defecto (seguro),
# salvo que se defina DEBUG=True a proposito. En local, encendido por defecto.
DEBUG = os.getenv('DEBUG', 'False' if ON_RAILWAY else 'True') == 'True'

ALLOWED_HOSTS = [
    h.strip()
    for h in os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
    if h.strip()
]

CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.getenv('CSRF_TRUSTED_ORIGINS', '').split(',') if o.strip()
]

# Dominios propios del proyecto: se aceptan SIEMPRE, sin depender de variables
# de entorno. El comodin (empezar con punto) cubre gym., www. y la raiz.
ALLOWED_HOSTS.append('.vitafitt.org')
CSRF_TRUSTED_ORIGINS.append('https://*.vitafitt.org')

# En Railway todo el trafico entra por su proxy sobre dominios *.railway.app:
# el propio dominio del servicio y el host del healthcheck.
if ON_RAILWAY:
    ALLOWED_HOSTS.append('.railway.app')
    CSRF_TRUSTED_ORIGINS.append('https://*.railway.app')

# Dominio publico concreto del servicio (por si Railway lo expone).
RAILWAY_DOMAIN = os.getenv('RAILWAY_PUBLIC_DOMAIN', '')
if RAILWAY_DOMAIN:
    ALLOWED_HOSTS.append(RAILWAY_DOMAIN)
    CSRF_TRUSTED_ORIGINS.append(f'https://{RAILWAY_DOMAIN}')


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Solo por intcomma: un total de cinco cifras sin separador no se lee.
    'django.contrib.humanize',

    'core',
    'accounts',
    'bot',
    'clientes',
    'entrenamiento',
    'inventario',
    'ventas',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # WhiteNoise sirve los estaticos ya comprimidos, justo despues de seguridad.
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.gym_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# En Railway se define DATABASE_URL al enlazar el servicio PostgreSQL.
# En local, sin esa variable, se usa SQLite.

import dj_database_url  # noqa: E402

DATABASE_URL = os.getenv('DATABASE_URL', '')
if DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,          # reusa conexiones entre peticiones
            ssl_require=not DEBUG,     # Railway exige SSL en produccion
        )
    }
elif os.getenv('POSTGRES_DB'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('POSTGRES_DB'),
            'USER': os.getenv('POSTGRES_USER', 'postgres'),
            'PASSWORD': os.getenv('POSTGRES_PASSWORD', ''),
            'HOST': os.getenv('POSTGRES_HOST', 'localhost'),
            'PORT': os.getenv('POSTGRES_PORT', '5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }


AUTH_USER_MODEL = 'accounts.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# Internationalization

LANGUAGE_CODE = 'es'

TIME_ZONE = 'America/Mexico_City'

USE_I18N = True

USE_TZ = True


# Static / media
#
# Estaticos: WhiteNoise, comprimidos y con hash, servidos por el propio Django.
# Media (fotos que suben los gimnasios): bucket S3 si hay credenciales; en local,
# el disco. Se separa a proposito porque los archivos subidos no sobreviven a un
# redeploy en Railway, mientras que un bucket es permanente.

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = 'media/'
# En Railway conviene apuntar MEDIA_ROOT al punto de montaje de un volumen
# (por ejemplo /data/media): el disco normal del contenedor se borra en cada
# redeploy y las fotos se perderian.
MEDIA_ROOT = Path(os.getenv('MEDIA_ROOT', '') or BASE_DIR / 'media')

# El manifest exige haber corrido collectstatic, asi que solo se usa en
# produccion. En desarrollo y en las pruebas se sirve directo, sin manifest.
_static_backend = (
    'django.contrib.staticfiles.storage.StaticFilesStorage'
    if DEBUG
    else 'whitenoise.storage.CompressedManifestStaticFilesStorage'
)

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': _static_backend,
    },
}

AWS_STORAGE_BUCKET_NAME = os.getenv('AWS_STORAGE_BUCKET_NAME', '')
if AWS_STORAGE_BUCKET_NAME:
    AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID', '')
    AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY', '')
    # Endpoint propio para buckets compatibles (Cloudflare R2, MinIO, etc.).
    AWS_S3_ENDPOINT_URL = os.getenv('AWS_S3_ENDPOINT_URL', '') or None
    # La region entra en la firma s3v4. R2 no tiene regiones: espera 'auto', y
    # una region vacia hace que Cloudflare rechace la subida por firma invalida.
    AWS_S3_REGION_NAME = (
        os.getenv('AWS_S3_REGION_NAME', '')
        or ('auto' if AWS_S3_ENDPOINT_URL else None)
    )
    # Aqui va SOLO el host. Se acepta pegado con esquema o barra final porque es
    # como lo copia Cloudflare, y un 'https://' de mas produce urls invalidas
    # del tipo https://https://bucket.r2.dev/foto.png.
    AWS_S3_CUSTOM_DOMAIN = (
        os.getenv('AWS_S3_CUSTOM_DOMAIN', '')
        .strip()
        .removeprefix('https://')
        .removeprefix('http://')
        .strip('/')
    ) or None
    # R2 firma con s3v4; es tambien el default de AWS, asi que no estorba.
    AWS_S3_SIGNATURE_VERSION = 's3v4'
    AWS_QUERYSTRING_AUTH = False        # las fotos son publicas, urls limpias
    AWS_S3_FILE_OVERWRITE = False       # no pisar un archivo con otro del mismo nombre
    AWS_DEFAULT_ACL = None              # R2 no maneja ACLs; se dejan sin definir
    AWS_S3_OBJECT_PARAMETERS = {'CacheControl': 'max-age=86400'}

    STORAGES['default'] = {'BACKEND': 'storages.backends.s3.S3Storage'}

    if AWS_S3_CUSTOM_DOMAIN:
        MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/'

# Sin bucket, las fotos viven en el disco y las tiene que servir Django: sin
# esto se guardan bien pero salen rotas en cuanto DEBUG=False.
SERVE_MEDIA = not AWS_STORAGE_BUCKET_NAME

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'core:dashboard'
LOGOUT_REDIRECT_URL = 'accounts:login'

MESSAGE_STORAGE = 'django.contrib.messages.storage.session.SessionStorage'


# Seguridad en produccion: solo cuando DEBUG=False

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    # El healthcheck de Railway golpea la app por HTTP interno; sin esta
    # excepcion, SECURE_SSL_REDIRECT le devuelve un 301 y el deploy falla.
    SECURE_REDIRECT_EXEMPT = [r'^salud/$']
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
