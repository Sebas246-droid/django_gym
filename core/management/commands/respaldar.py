"""
Copia de seguridad de la base local.

    python manage.py respaldar
    python manage.py respaldar --destino D:/respaldos --conservar 30

Usa la API de respaldo de SQLite, no un copiar y pegar del archivo: con WAL
encendido siempre hay escrituras a medio camino en el diario, y copiar el .db
suelto puede dar una base incompleta. La API espera a que la copia quede
consistente aunque alguien este cobrando en ese momento.

Pensado para el instalador: una tarea programada que lo corre cada noche deja
al gimnasio con respaldo sin que nadie se acuerde de hacerlo.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = 'Respalda la base de datos local en un archivo con fecha.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--destino',
            default='',
            help='Carpeta donde dejar el respaldo. Por omision, respaldos/ '
                 'junto a la base.',
        )
        parser.add_argument(
            '--conservar',
            type=int,
            default=14,
            help='Cuantos respaldos dejar. Los mas viejos se borran. 0 = todos.',
        )

    def handle(self, *args, **opciones):
        base = settings.DATABASES['default']
        if 'sqlite' not in base['ENGINE']:
            raise CommandError(
                'Este respaldo es para la edicion local con SQLite. '
                'Con PostgreSQL usa pg_dump.'
            )

        destino = Path(opciones['destino']) if opciones['destino'] else (
            self.carpeta_por_omision(base['NAME'])
        )
        destino.mkdir(parents=True, exist_ok=True)

        marca = datetime.now().strftime('%Y-%m-%d_%H%M%S')
        archivo = destino / f'gympilot_{marca}.sqlite3'

        # Se respalda la conexion que Django ya tiene abierta, no el archivo
        # buscado por su ruta: es la base que de verdad se esta usando.
        connection.ensure_connection()
        copia = sqlite3.connect(archivo)
        try:
            connection.connection.backup(copia)
        finally:
            copia.close()

        mb = archivo.stat().st_size / 1024 / 1024
        self.stdout.write(self.style.SUCCESS(f'Respaldo listo: {archivo} ({mb:.1f} MB)'))

        borrados = self.limpiar(destino, opciones['conservar'])
        if borrados:
            self.stdout.write(f'Se borraron {borrados} respaldos viejos.')

    @staticmethod
    def carpeta_por_omision(nombre_base):
        """Junto a la base si es un archivo; si no (pruebas en memoria), en el
        proyecto."""
        ruta = Path(str(nombre_base))
        if ruta.is_absolute() and ruta.parent.exists():
            return ruta.parent / 'respaldos'
        return Path(settings.BASE_DIR) / 'respaldos'

    def limpiar(self, destino, conservar):
        if conservar <= 0:
            return 0
        # Ordenados por fecha de modificacion y no por nombre: si alguien mueve
        # archivos a mano, el nombre puede mentir y la fecha no.
        respaldos = sorted(
            destino.glob('gympilot_*.sqlite3'),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        sobran = respaldos[conservar:]
        for viejo in sobran:
            viejo.unlink()
        return len(sobran)
