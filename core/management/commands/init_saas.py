"""
Inicializa el SaaS: roles (Groups), planes y, opcionalmente, un gym demo.

    python manage.py init_saas
    python manage.py init_saas --demo
"""

from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Gym, Plan, Sucursal
from core.roles import ADMINISTRADOR, ENTRENADOR, RECEPCION

# Modelos que puede tocar cada rol (app_label.model)
PERMISOS_ROL = {
    ADMINISTRADOR: {
        'core.gym': 'ru',
        'core.sucursal': 'crud',
        'core.gymimagen': 'crud',
        'accounts.user': 'crud',
        'clientes.cliente': 'crud',
        'clientes.membresia': 'crud',
        'clientes.clientemembresia': 'crud',
        'clientes.asistencia': 'crud',
        'entrenamiento.entrenamiento': 'crud',
        'inventario.categoriaproducto': 'crud',
        'inventario.producto': 'crud',
        'inventario.inventariosucursal': 'crud',
        'inventario.proveedor': 'crud',
        'inventario.compra': 'crud',
        'inventario.compradetalle': 'crud',
        'ventas.venta': 'crud',
        'ventas.ventadetalle': 'crud',
    },
    RECEPCION: {
        'clientes.cliente': 'crud',
        'clientes.membresia': 'r',
        'clientes.clientemembresia': 'crud',
        'clientes.asistencia': 'crud',
        'entrenamiento.entrenamiento': 'r',
        'inventario.producto': 'r',
        'inventario.inventariosucursal': 'r',
        'ventas.venta': 'crud',
        'ventas.ventadetalle': 'crud',
    },
    ENTRENADOR: {
        'clientes.cliente': 'r',
        'clientes.asistencia': 'cr',
        'entrenamiento.entrenamiento': 'crud',
    },
}

ACCIONES = {'c': 'add', 'r': 'view', 'u': 'change', 'd': 'delete'}


class Command(BaseCommand):
    help = 'Crea roles, planes base y datos demo del SaaS.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--demo',
            action='store_true',
            help='Crea un gimnasio demo con su administrador.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        self.crear_roles()
        self.crear_planes()
        if options['demo']:
            self.crear_demo()
        self.stdout.write(self.style.SUCCESS('SaaS inicializado.'))

    def crear_roles(self):
        for rol, modelos in PERMISOS_ROL.items():
            grupo, creado = Group.objects.get_or_create(name=rol)
            permisos = []
            for etiqueta, acciones in modelos.items():
                app_label, modelo = etiqueta.split('.')
                for letra in acciones:
                    codename = f'{ACCIONES[letra]}_{modelo}'
                    permiso = Permission.objects.filter(
                        content_type__app_label=app_label, codename=codename
                    ).first()
                    if permiso:
                        permisos.append(permiso)
            grupo.permissions.set(permisos)
            estado = 'creado' if creado else 'actualizado'
            self.stdout.write(f'  Rol {rol}: {estado} ({len(permisos)} permisos)')

    def crear_planes(self):
        planes = [
            ('Basico', 500, 2, 100, 1),
            ('Pro', 1200, 6, 500, 3),
            ('Premium', 2500, 20, 5000, 10),
        ]
        for nombre, precio, usuarios, clientes, sucursales in planes:
            plan, creado = Plan.objects.get_or_create(
                nombre=nombre,
                defaults={
                    'precio': precio,
                    'usuarios_max': usuarios,
                    'clientes_max': clientes,
                    'sucursales_max': sucursales,
                },
            )
            if creado:
                self.stdout.write(f'  Plan {plan.nombre} creado')

    def crear_demo(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        plan = Plan.objects.get(nombre='Pro')
        gym, creado = Gym.objects.get_or_create(
            nombre='Gimnasio Demo',
            defaults={'plan': plan, 'email': 'demo@gympilot.test'},
        )
        sucursal = Sucursal.objects.filter(gym=gym).first()

        if not User.objects.filter(username='admin_demo').exists():
            admin = User.objects.create_user(
                username='admin_demo',
                password='demo12345',
                first_name='Admin',
                last_name='Demo',
                gym=gym,
                sucursal=sucursal,
            )
            admin.groups.add(Group.objects.get(name=ADMINISTRADOR))
            self.stdout.write('  Usuario admin_demo / demo12345 creado')

        if not User.objects.filter(username='recepcion_demo').exists():
            recepcion = User.objects.create_user(
                username='recepcion_demo',
                password='demo12345',
                first_name='Recepcion',
                last_name='Demo',
                gym=gym,
                sucursal=sucursal,
            )
            recepcion.groups.add(Group.objects.get(name=RECEPCION))
            self.stdout.write('  Usuario recepcion_demo / demo12345 creado')

        if creado:
            self.stdout.write(f'  Gym demo creado con sucursal {sucursal}')
        self.contenido_demo(gym, sucursal)

    def contenido_demo(self, gym, sucursal):
        """Sitio publico, membresias y clientes para poder probar el acceso."""
        from datetime import timedelta

        from django.utils import timezone

        from clientes.models import Cliente, ClienteMembresia, Membresia
        from entrenamiento.models import Entrenamiento

        gym.frase_principal = 'Fitness para atletas de todos los dias'
        gym.telefono = '52 55 1234 5678'
        gym.save()

        sucursal.direccion = 'Av. Reforma 100, Centro'
        sucursal.telefono = '55 1234 5678'
        sucursal.latitud = 19.432608
        sucursal.longitud = -99.133209
        sucursal.save()

        for nombre, descripcion in [
            ('Funcional', 'Circuito de fuerza y resistencia en 45 minutos.'),
            ('Spinning', 'Cardio en bici con instructor.'),
            ('Pesas libres', 'Rutina guiada de hipertrofia.'),
        ]:
            Entrenamiento.objects.get_or_create(
                gym=gym, nombre=nombre, defaults={'descripcion': descripcion}
            )

        mensual, _ = Membresia.objects.get_or_create(
            gym=gym, nombre='Mensual',
            defaults={'precio': 600, 'duracion_dias': 30},
        )
        Membresia.objects.get_or_create(
            gym=gym, nombre='Anual',
            defaults={'precio': 6000, 'duracion_dias': 365},
        )

        self.catalogo_demo(gym, sucursal)

        hoy = timezone.localdate()
        demo = [
            ('Ana Torres', hoy),                       # vigente
            ('Luis Ramirez', hoy - timedelta(days=28)),  # por vencer
            ('Sofia Mendez', hoy - timedelta(days=90)),  # vencida
            ('Carlos Vega', None),                     # sin membresia
            ('Diego Herrera', hoy - timedelta(days=5)),
            ('Paola Nunez', hoy - timedelta(days=12)),
        ]
        creados = []
        for nombre, inicio in demo:
            cliente, nuevo = Cliente.objects.get_or_create(
                gym=gym, nombre=nombre, defaults={'sucursal': sucursal}
            )
            if nuevo and inicio:
                ClienteMembresia.objects.create(
                    gym=gym, cliente=cliente, membresia=mensual,
                    inicio=inicio, precio=mensual.precio,
                )
            creados.append(cliente)
            if nuevo:
                self.stdout.write(
                    f'  Cliente {cliente.nombre} numero {cliente.numero_usuario}'
                )

        self.actividad_demo(gym, sucursal, creados)

    def actividad_demo(self, gym, sucursal, clientes):
        """
        Asistencias y una venta de los ultimos dias. Sin esto el tablero se
        ve vacio, que es justo la pantalla que se ensena al presentar.
        """
        import random
        from datetime import timedelta

        from django.utils import timezone

        from clientes.models import Asistencia
        from inventario.models import Producto
        from ventas.models import Venta, VentaDetalle

        if Asistencia.objects.filter(gym=gym).exists():
            return

        random.seed(7)
        ahora = timezone.localtime()
        usuario = gym.users.filter(is_active=True).first()

        for atras in range(6, -1, -1):
            dia = ahora - timedelta(days=atras)
            for cliente in random.sample(clientes, k=random.randint(1, len(clientes))):
                entrada = dia.replace(
                    hour=random.randint(7, 20), minute=random.choice([0, 15, 30, 45])
                )
                Asistencia.objects.create(
                    gym=gym, sucursal=sucursal, cliente=cliente, usuario=usuario,
                    fecha_hora=entrada, tipo=Asistencia.ENTRADA,
                )
                # La mayoria ya salio; algunos de hoy siguen dentro
                if atras > 0 or random.random() < 0.5:
                    Asistencia.objects.create(
                        gym=gym, sucursal=sucursal, cliente=cliente, usuario=usuario,
                        fecha_hora=entrada + timedelta(hours=1, minutes=20),
                        tipo=Asistencia.SALIDA,
                    )

        productos = list(Producto.objects.filter(gym=gym, activo=True)[:4])
        if productos:
            venta = Venta.objects.create(
                gym=gym, sucursal=sucursal, usuario=usuario,
                cliente=clientes[0], metodo_pago='efectivo',
            )
            for producto in productos[:2]:
                VentaDetalle.objects.create(
                    venta=venta, producto=producto,
                    cantidad=random.randint(1, 3), precio=producto.precio_venta,
                )
            venta.confirmar()
            self.stdout.write('  Actividad de demostracion creada')

    def catalogo_demo(self, gym, sucursal):
        """Productos con existencias para poder probar el punto de venta."""
        from inventario.models import CategoriaProducto, InventarioSucursal, Producto

        catalogo = [
            ('Suplementos', 'Proteina Whey 2kg', 'MuscleTech', 890, 12),
            ('Suplementos', 'Creatina 300g', 'ON', 450, 7),
            ('Bebidas', 'Agua 600ml', 'Ciel', 15, 48),
            ('Bebidas', 'Bebida isotonica', 'Gatorade', 28, 24),
            ('Bebidas', 'Cafe americano', '', 35, 3),
            ('Accesorios', 'Guantes de gimnasio', 'Nike', 340, 5),
            ('Accesorios', 'Shaker 700ml', '', 120, 0),
            ('Accesorios', 'Banda elastica', 'Everlast', 180, 9),
        ]
        for i, (cat, nombre, marca, precio, stock) in enumerate(catalogo):
            categoria, _ = CategoriaProducto.objects.get_or_create(
                gym=gym, nombre=cat
            )
            producto, nuevo = Producto.objects.get_or_create(
                gym=gym,
                codigo=f'D{i:03d}',
                defaults={
                    'categoria': categoria,
                    'nombre': nombre,
                    'marca': marca,
                    'precio_compra': round(precio * 0.6, 2),
                    'precio_venta': precio,
                },
            )
            if nuevo:
                InventarioSucursal.objects.update_or_create(
                    producto=producto,
                    sucursal=sucursal,
                    defaults={'stock': stock, 'stock_minimo': 4},
                )
