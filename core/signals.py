from django.db.models.signals import post_save
from django.dispatch import receiver

from core.models import Gym, Sucursal


@receiver(post_save, sender=Gym)
def crear_sucursal_principal(sender, instance, created, **kwargs):
    """Al dar de alta un gimnasio se crea automaticamente su sucursal Principal."""
    if created:
        Sucursal.objects.create(gym=instance, nombre='Principal')
