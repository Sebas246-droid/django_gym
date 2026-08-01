"""Reglas para los archivos que suben los gimnasios."""

import uuid
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.utils.deconstruct import deconstructible

#: Lo que de verdad llega como comprobante: foto del ticket o PDF del banco.
#: HEIC entra porque es lo que manda un iPhone sin convertir.
EXTENSIONES_COMPROBANTE = ['jpg', 'jpeg', 'png', 'webp', 'heic', 'heif', 'pdf']

#: Una foto de celular ronda los 3 o 4 MB. Diez deja margen sin permitir que
#: alguien llene el bucket con un video por error.
MAXIMO_MB = 10


def no_pesar_de_mas(archivo):
    if archivo.size > MAXIMO_MB * 1024 * 1024:
        raise ValidationError(
            f'El archivo pesa {archivo.size / 1024 / 1024:.1f} MB '
            f'y el limite son {MAXIMO_MB} MB.'
        )


validar_comprobante = [
    FileExtensionValidator(EXTENSIONES_COMPROBANTE),
    no_pesar_de_mas,
]


@deconstructible
class RutaPorGym:
    """
    Guarda en <carpeta>/<gym>/<nombre al azar>.<ext>.

    El nombre original no se conserva a proposito. Los comprobantes viven en un
    bucket publico, igual que las fotos, y un "comprobante.jpg" seria una url
    que cualquiera adivina. Con un uuid hay que tener el enlace para verlo.
    """

    def __init__(self, carpeta):
        self.carpeta = carpeta

    def __call__(self, instancia, nombre):
        extension = Path(nombre).suffix.lower()
        return f'{self.carpeta}/{instancia.gym_id}/{uuid.uuid4().hex}{extension}'

    def __eq__(self, otro):
        return isinstance(otro, RutaPorGym) and otro.carpeta == self.carpeta
