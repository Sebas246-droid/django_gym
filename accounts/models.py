from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Autenticacion nativa de Django. Los roles se manejan con Groups.
    gym = None significa super administrador del SaaS.
    """

    gym = models.ForeignKey(
        'core.Gym',
        on_delete=models.CASCADE,
        related_name='users',
        null=True,
        blank=True,
    )
    sucursal = models.ForeignKey(
        'core.Sucursal',
        on_delete=models.SET_NULL,
        related_name='users',
        null=True,
        blank=True,
    )
    telefono = models.CharField(max_length=30, blank=True)
    foto = models.ImageField(upload_to='usuarios/', blank=True, null=True)

    class Meta:
        ordering = ['username']
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'

    def __str__(self):
        nombre = self.get_full_name()
        return nombre or self.username

    @property
    def rol(self):
        if self.is_superuser and self.gym_id is None:
            return 'Super Administrador'
        grupo = self.groups.first()
        return grupo.name if grupo else 'Sin rol'
