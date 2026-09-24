"""
Crea gimnasios de prueba, cada uno con su administrador y datos dentro.

    python manage.py crear_demos                      # 15, como vienen
    python manage.py crear_demos --cantidad 5
    python manage.py crear_demos > credenciales.csv   # las guarda

Sirve para ensenar el sistema: un prospecto entra a su propio gimnasio, con
socios, membresias, accesos y ventas ya cargados, y no ve los datos de nadie
mas.

No toca nada de lo que ya existe. Si un gimnasio con ese nombre ya esta, lo
salta y lo dice: correrlo dos veces no duplica ni reescribe.

Las contrasenas salen al azar y se imprimen UNA sola vez, en el csv de la
salida. No quedan guardadas en ningun lado: Django solo guarda su huella. Si se
pierden, hay que volver a generarlas.

El csv va por la salida normal y los avisos por la de errores, para que
redirigir a un archivo deje el csv limpio y los avisos en pantalla.

La pagina publica de los gimnasios de prueba nace APAGADA, y no es un descuido:
la raiz del dominio lleva a la pagina del gimnasio solo mientras haya uno solo
publicado. Con quince mas encendidos, vitafitt.org dejaria de abrir el gimnasio
de verdad y caeria en el login. Para ensenar tambien esa pantalla, se prende la
de un gimnasio desde su propio panel, en Sitio web, o se corre con --con-sitio
sabiendo lo anterior.
"""

import csv
import secrets

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction

from core.management.commands.init_saas import Command as InitSaas
from core.models import Gym, Plan, Sucursal
from core.roles import ADMINISTRADOR

User = get_user_model()

#: Nombres genericos y numerados. Sin marcas inventadas: un nombre que suene a
#: gimnasio de verdad se confunde con un cliente de verdad en la lista del
#: panel, y ahi si importa saber cual es cual. El nombre se le cambia a cada
#: uno desde su panel cuando se le ensene a un prospecto.
NOMBRES = [f'Gimnasio Demo {i:02d}' for i in range(1, 21)]

#: Se reparten para que la demostracion ensene los tres planes.
PLANES = ['Basico', 'Pro', 'Premium']


class Command(BaseCommand):
    help = 'Crea gimnasios de prueba con datos y su administrador.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--cantidad', type=int, default=15,
            help='Cuantos crear. Por omision 15.',
        )
        parser.add_argument(
            '--dominio', default='gym.vitafitt.org',
            help='Donde entra el administrador. Solo se usa para armar la url.',
        )
        parser.add_argument(
            '--desde',
            help='Un csv con gimnasio,plan,usuario,contrasena, del mismo '
                 'formato que sale de aqui. Crea exactamente esos, con esas '
                 'contrasenas, en vez de inventarlas.',
        )
        parser.add_argument(
            '--con-sitio', action='store_true',
            help='Publica tambien la pagina publica de cada gimnasio de prueba. '
                 'Apagado por omision: ver el aviso del encabezado.',
        )

    @transaction.atomic
    def handle(self, *args, **opciones):
        cantidad = max(opciones['cantidad'], 0)
        dominio = opciones['dominio'].strip().strip('/')
        if cantidad > len(NOMBRES):
            self.stderr.write(
                f'Solo hay {len(NOMBRES)} nombres preparados; se crean esos.'
            )
            cantidad = len(NOMBRES)

        # El catalogo de roles y planes tiene que existir antes que los gyms.
        init = InitSaas()
        # Lo que cuenta init_saas mientras trabaja va a la salida de errores,
        # o se mete en medio del csv al redirigirlo a un archivo.
        init.stdout = self.stderr
        init.crear_roles()
        init.crear_planes()

        salida = csv.writer(self.stdout)
        salida.writerow(
            ['gimnasio', 'plan', 'usuario', 'contrasena', 'panel', 'sitio publico']
        )

        creados = saltados = 0
        for nombre, plan_nombre, usuario, contrasena in _por_crear(
            opciones['desde'], cantidad
        ):
            gym = Gym.objects.filter(nombre=nombre).first()
            if gym:
                # Ya estaba de una corrida anterior, o es un cliente de verdad.
                # En los dos casos, no se toca ni se ensena su contrasena.
                self.stderr.write(f'  {nombre}: ya existe, se deja como esta.')
                saltados += 1
                continue

            plan = Plan.objects.get(nombre=plan_nombre)
            gym = Gym.objects.create(
                nombre=nombre, plan=plan, email=f'contacto@{_correo(nombre)}.mx',
                sitio_publico=opciones['con_sitio'],
            )
            sucursal = Sucursal.objects.filter(gym=gym).first()

            admin = User.objects.create_user(
                username=usuario, password=contrasena,
                first_name='Admin', last_name=nombre,
                gym=gym, sucursal=sucursal,
            )
            admin.groups.add(Group.objects.get(name=ADMINISTRADOR))

            # Socios, membresias, accesos, productos y ventas de los ultimos
            # dias: es lo que hace que el tablero no se vea vacio al ensenarlo.
            init.contenido_demo(gym, sucursal)

            salida.writerow([
                nombre, plan.nombre, usuario, contrasena,
                f'https://{dominio}/cuentas/login/',
                f'https://{dominio}/g/{gym.slug}/' if opciones['con_sitio']
                else 'apagada',
            ])
            self.stderr.write(f'  {nombre}: listo ({plan.nombre}, {usuario})')
            creados += 1

        self.stdout.flush()
        self.stderr.write(
            self.style.SUCCESS(
                f'\n{creados} gimnasios creados, {saltados} saltados.\n'
                'Las contrasenas van arriba y no se pueden volver a consultar: '
                'guardalas antes de cerrar esta ventana.'
            )
        )


def _por_crear(archivo, cantidad):
    """
    Que gimnasios hay que crear: (nombre, plan, usuario, contrasena).

    Con un csv se crean esos, tal cual, con sus contrasenas. Sirve para que la
    hoja de credenciales se prepare antes y lo que quede en produccion coincida
    con ella. Sin csv, se inventan.
    """
    if archivo:
        with open(archivo, newline='', encoding='utf-8') as datos:
            return [
                (f['gimnasio'].strip(), f['plan'].strip(),
                 f['usuario'].strip(), f['contrasena'].strip())
                for f in csv.DictReader(datos)
            ]

    return [
        (nombre, PLANES[i % len(PLANES)], f'demo{i + 1:02d}',
         secrets.token_urlsafe(9))
        for i, nombre in enumerate(NOMBRES[:cantidad])
    ]


def _correo(nombre):
    """El nombre en algo que se pueda poner antes del punto de un correo."""
    limpio = ''.join(c for c in nombre.lower() if c.isalnum() or c == ' ')
    return limpio.replace(' ', '')
