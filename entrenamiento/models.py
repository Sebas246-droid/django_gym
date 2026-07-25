from django.db import models

from core.models import GymModel


class Entrenamiento(GymModel):
    """
    Catalogo configurable por cada gimnasio.
    En fase 2 la IA usara este registro para enviar PDF, videos y rutinas.
    """

    nombre = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True)
    documento = models.FileField(upload_to='entrenamientos/docs/', blank=True, null=True)
    video = models.URLField(blank=True)

    class Meta:
        ordering = ['nombre']
        verbose_name = 'Entrenamiento'
        verbose_name_plural = 'Entrenamientos'

    def __str__(self):
        return self.nombre
