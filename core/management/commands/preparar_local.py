"""
Deja lista una instalacion local en el primer arranque.

    python manage.py preparar_local --gimnasio "Iron House" --admin dueno

Crea roles, planes, el unico gimnasio de esta instalacion con su sucursal
Principal, y el usuario administrador que va a usar el dueno. Es idempotente:
el instalador lo corre en cada arranque y solo completa lo que falte, nunca
duplica ni pisa datos.

A diferencia del SaaS aqui NO se crea un superusuario de Django: el dueno del
gimnasio entra como administrador de su gym. Asi no ve el panel de gimnasios y
planes, que en esta edicion no significa nada.
"""

import io
import os
import secrets
import string

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Gym, Plan, Sucursal
from core.roles import ADMINISTRADOR

User = get_user_model()

#: El plan no limita nada en local: el gimnasio ya pago. Se le pone el mas
#: holgado para que ningun tope del SaaS le estorbe.
PLAN_LOCAL = 'Premium'


def contrasena_al_azar(largo=12):
    alfabeto = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alfabeto) for _ in range(largo))


class Command(BaseCommand):
    help = 'Prepara la instalacion local: gimnasio, sucursal y administrador.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--gimnasio',
            default=os.getenv('GIMNASIO_NOMBRE', 'Mi Gimnasio'),
            help='Nombre del gimnasio. Se puede cambiar despues desde el sistema.',
        )
        parser.add_argument(
            '--sucursal',
            default=os.getenv('SUCURSAL_NOMBRE', 'Principal'),
            help='Nombre de la sucursal inicial.',
        )
        parser.add_argument(
            '--admin',
            default=os.getenv('ADMIN_USUARIO', 'admin'),
            help='Usuario del administrador.',
        )
        parser.add_argument(
            '--password',
            default=os.getenv('ADMIN_PASSWORD', ''),
            help='Contrasena del administrador. Si se omite se genera una y se '
                 'imprime una sola vez.',
        )

    @transaction.atomic
    def handle(self, *args, **opciones):
        # Roles y planes son los mismos que en el SaaS: se reusa el comando en
        # vez de copiar la tabla de permisos, que es donde se van las diferencias.
        # Su salida se tira: al dueno de un gimnasio no le dice nada, y hablar de
        # "SaaS" en una instalacion que compro una sola vez confunde.
        call_command('init_saas', stdout=io.StringIO())

        gym = self.gimnasio(opciones['gimnasio'])
        sucursal = self.sucursal(gym, opciones['sucursal'])
        self.administrador(gym, sucursal, opciones['admin'], opciones['password'])

        self.stdout.write(self.style.SUCCESS('\nInstalacion lista.'))

    def gimnasio(self, nombre):
        gym = Gym.objects.first()
        if gym:
            self.stdout.write(f'  Gimnasio: {gym.nombre} (ya existia)')
            return gym
        gym = Gym.objects.create(
            nombre=nombre, plan=Plan.objects.get(nombre=PLAN_LOCAL)
        )
        self.stdout.write(self.style.SUCCESS(f'  Gimnasio: {gym.nombre} (creado)'))
        return gym

    def sucursal(self, gym, nombre):
        """
        El alta de un gimnasio ya crea su sucursal Principal. Aqui solo se
        toma la que exista, para no dejar dos sedes en una instalacion que casi
        siempre es de un local.
        """
        sucursal = Sucursal.objects.filter(gym=gym).order_by('pk').first()
        if sucursal:
            self.stdout.write(f'  Sucursal: {sucursal.nombre} (ya existia)')
            return sucursal
        sucursal = Sucursal.objects.create(gym=gym, nombre=nombre)
        self.stdout.write(self.style.SUCCESS(f'  Sucursal: {sucursal.nombre} (creada)'))
        return sucursal

    def administrador(self, gym, sucursal, username, password):
        usuario = User.objects.filter(username=username).first()
        if usuario:
            self.stdout.write(f'  Administrador: {username} (ya existia, sin tocar)')
            return usuario

        generada = not password
        password = password or contrasena_al_azar()
        usuario = User.objects.create_user(
            username=username, password=password, gym=gym, sucursal=sucursal
        )
        usuario.groups.add(Group.objects.get(name=ADMINISTRADOR))

        self.stdout.write(self.style.SUCCESS(f'  Administrador: {username} (creado)'))
        if generada:
            # Se imprime una vez y no se guarda en ningun lado: el instalador la
            # muestra al terminar y el dueno la cambia al entrar.
            self.stdout.write(self.style.WARNING(f'  Contrasena: {password}'))
            self.stdout.write('  Anotala: no se vuelve a mostrar.')
        return usuario
