"""
Diagnostico del almacenamiento de fotos. Sube un archivo de prueba, pide su URL
publica y comprueba que se pueda descargar; despues lo borra.

    python manage.py revisar_media

Pensado para correrlo en produccion cuando las fotos "no se guardan": distingue
los dos fallos que se ven igual desde el navegador, subida rechazada por el
bucket y subida correcta pero URL no publica.
"""

from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand

RUTA_PRUEBA = 'diagnostico/prueba-media.txt'


class Command(BaseCommand):
    help = 'Comprueba de punta a punta que las fotos se suban y se puedan ver.'

    def handle(self, *args, **options):
        self._configuracion()

        nombre = None
        try:
            nombre = default_storage.save(RUTA_PRUEBA, ContentFile(b'gympilot'))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f'\nNo se pudo subir: {exc}'))
            self.stdout.write(
                'La subida la rechaza el bucket. Revisa llaves, nombre del '
                'bucket y AWS_S3_ENDPOINT_URL.'
            )
            return

        self.stdout.write(self.style.SUCCESS(f'\nSubida OK: {nombre}'))

        url = default_storage.url(nombre)
        self.stdout.write(f'URL publica: {url}')
        self._descargar(url)

        default_storage.delete(nombre)
        self.stdout.write('Archivo de prueba borrado.')

    def _configuracion(self):
        backend = settings.STORAGES['default']['BACKEND']
        self.stdout.write(f'Backend      : {backend}')
        self.stdout.write(f'MEDIA_URL    : {settings.MEDIA_URL}')

        if 'S3Storage' not in backend:
            self.stdout.write(f'MEDIA_ROOT   : {settings.MEDIA_ROOT}')
            self.stdout.write(
                self.style.WARNING(
                    'Sin bucket: las fotos van al disco y se borran en cada '
                    'redeploy salvo que MEDIA_ROOT apunte a un volumen.'
                )
            )
            return

        self.stdout.write(f'Bucket       : {settings.AWS_STORAGE_BUCKET_NAME}')
        self.stdout.write(f'Endpoint     : {settings.AWS_S3_ENDPOINT_URL}')
        self.stdout.write(f'Region       : {settings.AWS_S3_REGION_NAME}')
        self.stdout.write(f'Dominio publico: {settings.AWS_S3_CUSTOM_DOMAIN}')

        if settings.AWS_S3_ENDPOINT_URL and not settings.AWS_S3_CUSTOM_DOMAIN:
            self.stdout.write(
                self.style.WARNING(
                    'Sin AWS_S3_CUSTOM_DOMAIN las URLs apuntan al endpoint '
                    'privado del bucket y el navegador recibe 401/403.'
                )
            )

    def _descargar(self, url):
        if not url.startswith('http'):
            self.stdout.write(
                self.style.WARNING('URL relativa: la sirve Django, no un bucket.')
            )
            return

        try:
            with urlopen(url, timeout=15) as respuesta:
                codigo = respuesta.status
        except HTTPError as exc:
            codigo = exc.code
        except URLError as exc:
            self.stdout.write(self.style.ERROR(f'No se pudo abrir la URL: {exc.reason}'))
            return

        if codigo == 200:
            self.stdout.write(self.style.SUCCESS(f'Descarga OK ({codigo}).'))
            self.stdout.write('El almacenamiento funciona de punta a punta.')
        else:
            self.stdout.write(self.style.ERROR(f'La URL responde {codigo}.'))
            self.stdout.write(
                'El archivo se subio pero no es publico. En R2: activa el '
                'dominio r2.dev del bucket o conectale un dominio propio, y '
                'pon ese host en AWS_S3_CUSTOM_DOMAIN.'
            )
