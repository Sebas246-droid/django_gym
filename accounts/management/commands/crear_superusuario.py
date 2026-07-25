"""
Crea (o actualiza) el super administrador del SaaS a partir de variables de
entorno. Pensado para produccion, donde no hay shell interactivo.

    SUPERUSER_USERNAME, SUPERUSER_EMAIL, SUPERUSER_PASSWORD

Es idempotente: si el usuario ya existe, solo actualiza su contrasena.
"""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()


class Command(BaseCommand):
    help = 'Crea el super administrador desde variables de entorno.'

    def handle(self, *args, **options):
        username = os.getenv('SUPERUSER_USERNAME')
        password = os.getenv('SUPERUSER_PASSWORD')
        email = os.getenv('SUPERUSER_EMAIL', '')

        if not username or not password:
            self.stdout.write(
                'SUPERUSER_USERNAME o SUPERUSER_PASSWORD sin definir: no se crea nada.'
            )
            return

        usuario, creado = User.objects.get_or_create(
            username=username,
            defaults={'email': email, 'is_staff': True, 'is_superuser': True},
        )
        usuario.email = email or usuario.email
        usuario.is_staff = True
        usuario.is_superuser = True
        usuario.set_password(password)
        usuario.save()

        estado = 'creado' if creado else 'actualizado'
        self.stdout.write(self.style.SUCCESS(f'Super administrador {estado}: {username}'))
