"""Prueba de humo del flujo completo descrito en el README."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from clientes.models import Asistencia, Cliente, ClienteMembresia, Membresia
from core.models import Gym, Plan, Sucursal
from core.roles import ADMINISTRADOR
from core.views import DashboardView
from inventario.models import (
    CategoriaProducto,
    InventarioSucursal,
    Movimiento,
    Producto,
)
from ventas.models import Venta, VentaDetalle

User = get_user_model()


class FlujoCompletoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('init_saas')

        # 1. Alta de gimnasio (crea sucursal Principal por signal)
        cls.gym = Gym.objects.create(nombre='Iron House', plan=Plan.objects.get(nombre='Pro'))
        cls.sucursal = Sucursal.objects.get(gym=cls.gym, nombre='Principal')

        # 2. Alta del usuario administrador
        cls.admin = User.objects.create_user(
            username='admin', password='pass12345',
            gym=cls.gym, sucursal=cls.sucursal,
        )
        cls.admin.groups.add(Group.objects.get(name=ADMINISTRADOR))

        # Gym vecino: sirve para comprobar el aislamiento de datos
        cls.otro_gym = Gym.objects.create(
            nombre='Otro Gym', plan=Plan.objects.get(nombre='Basico')
        )
        cls.otro_cliente = Cliente.objects.create(
            gym=cls.otro_gym,
            sucursal=Sucursal.objects.get(gym=cls.otro_gym),
            nombre='Cliente Ajeno',
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def test_sucursal_principal_automatica(self):
        self.assertEqual(self.gym.sucursales.count(), 1)
        self.assertEqual(self.sucursal.nombre, 'Principal')

    def test_dashboard_responde(self):
        respuesta = self.client.get(reverse('core:dashboard'))
        self.assertEqual(respuesta.status_code, 200)

    def test_el_tablero_cuenta_quien_sigue_dentro(self):
        """Sigue dentro quien su ultimo movimiento de hoy fue una entrada."""
        dentro = Cliente.objects.create(
            gym=self.gym, sucursal=self.sucursal, nombre='Sigue Dentro'
        )
        ya_salio = Cliente.objects.create(
            gym=self.gym, sucursal=self.sucursal, nombre='Ya Salio'
        )
        Asistencia.objects.create(
            gym=self.gym, sucursal=self.sucursal, cliente=dentro,
            tipo=Asistencia.ENTRADA,
        )
        Asistencia.objects.create(
            gym=self.gym, sucursal=self.sucursal, cliente=ya_salio,
            tipo=Asistencia.ENTRADA,
        )
        Asistencia.objects.create(
            gym=self.gym, sucursal=self.sucursal, cliente=ya_salio,
            tipo=Asistencia.SALIDA,
        )

        respuesta = self.client.get(reverse('core:dashboard'))

        self.assertEqual(respuesta.context['dentro_ahora'], 1)
        self.assertEqual(respuesta.context['asistencias_hoy'], 2)

    def test_la_salud_de_la_cartera_reparte_a_los_clientes(self):
        vigente = Cliente.objects.create(
            gym=self.gym, sucursal=self.sucursal, nombre='Vigente'
        )
        proximo = Cliente.objects.create(
            gym=self.gym, sucursal=self.sucursal, nombre='Por Vencer'
        )
        Cliente.objects.create(
            gym=self.gym, sucursal=self.sucursal, nombre='Sin Nada'
        )
        membresia = Membresia.objects.create(
            gym=self.gym, nombre='Mensual', precio=600, duracion_dias=30
        )
        hoy = timezone.localdate()
        ClienteMembresia.objects.create(
            gym=self.gym, cliente=vigente, membresia=membresia,
            inicio=hoy, precio=600,
        )
        ClienteMembresia.objects.create(
            gym=self.gym, cliente=proximo, membresia=membresia,
            inicio=hoy - timezone.timedelta(days=27), precio=600,
        )

        ctx = self.client.get(reverse('core:dashboard')).context

        self.assertEqual(ctx['al_corriente'], 1)
        self.assertEqual(ctx['por_vencer_total'], 1)
        self.assertEqual(ctx['sin_membresia'], 1)
        self.assertEqual(ctx['salud']['cobertura'], 67)

    def test_la_grafica_trae_siete_dias_con_coordenadas(self):
        ctx = self.client.get(reverse('core:dashboard')).context

        puntos = ctx['grafica']['puntos']
        self.assertEqual(len(puntos), 7)
        self.assertTrue(puntos[-1]['hoy'])
        # Ningun punto se sale del area dibujable
        for punto in puntos:
            self.assertGreaterEqual(punto['y'], DashboardView.TECHO)
            self.assertLessEqual(punto['y'], DashboardView.PISO)

    def test_alta_de_usuario_con_rol(self):
        respuesta = self.client.post(
            reverse('accounts:usuario_create'),
            {
                'username': 'recepcion1',
                'first_name': 'Ana',
                'last_name': 'Perez',
                'email': 'ana@test.com',
                'telefono': '5512345678',
                'sucursal': self.sucursal.pk,
                'rol': Group.objects.get(name='Recepcion - Caja').pk,
                'password1': 'clave-segura-123',
                'password2': 'clave-segura-123',
            },
        )
        self.assertEqual(respuesta.status_code, 302)
        usuario = User.objects.get(username='recepcion1')
        self.assertEqual(usuario.gym, self.gym)
        self.assertEqual(usuario.rol, 'Recepcion - Caja')

    def test_registro_de_cliente(self):
        respuesta = self.client.post(
            reverse('clientes:cliente_create'),
            {'nombre': 'Juan Lopez', 'sucursal': self.sucursal.pk, 'telefono': '5500000000'},
        )
        self.assertEqual(respuesta.status_code, 302)
        cliente = Cliente.objects.get(nombre='Juan Lopez')
        self.assertEqual(cliente.gym, self.gym)

    def test_venta_de_membresia_calcula_vigencia_y_cobro(self):
        cliente = Cliente.objects.create(
            gym=self.gym, sucursal=self.sucursal, nombre='Maria Ruiz'
        )
        membresia = Membresia.objects.create(
            gym=self.gym, nombre='Mensual', precio=600, duracion_dias=30
        )
        respuesta = self.client.post(
            reverse('clientes:clientemembresia_create'),
            {
                'cliente': cliente.pk,
                'membresia': membresia.pk,
                'inicio': '2026-01-01',
                'precio': '600',
                'descuento': '50',
                'metodo_pago': 'efectivo',
                'observaciones': '',
            },
        )
        self.assertEqual(respuesta.status_code, 302)
        cm = ClienteMembresia.objects.get(cliente=cliente)
        self.assertEqual(str(cm.fin), '2026-01-31')
        self.assertEqual(cm.total, 550)
        self.assertEqual(cm.usuario, self.admin)  # queda registrado quien cobro

    def test_checkin_registra_asistencia(self):
        cliente = Cliente.objects.create(
            gym=self.gym, sucursal=self.sucursal, nombre='Pedro Diaz'
        )
        respuesta = self.client.post(
            reverse('clientes:asistencia_registrar', args=[cliente.pk]),
            {'tipo': 'entrada', 'entrenamiento': '', 'q': 'Pedro'},
        )
        self.assertEqual(respuesta.status_code, 302)
        asistencia = Asistencia.objects.get(cliente=cliente)
        self.assertEqual(asistencia.tipo, Asistencia.ENTRADA)
        self.assertEqual(asistencia.usuario, self.admin)

    def test_una_entrada_suma_stock(self):
        categoria = CategoriaProducto.objects.create(gym=self.gym, nombre='Suplementos')
        producto = Producto.objects.create(
            gym=self.gym, categoria=categoria, codigo='P001',
            nombre='Proteina', precio_compra=300, precio_venta=500,
        )

        respuesta = self.client.post(reverse('inventario:movimiento_create'), {
            'producto': producto.pk, 'sucursal': self.sucursal.pk,
            'tipo': 'entrada', 'motivo': 'compra',
            'cantidad': '10', 'precio': '300',
        })
        self.assertEqual(respuesta.status_code, 302)

        inventario = InventarioSucursal.objects.get(
            producto=producto, sucursal=self.sucursal
        )
        self.assertEqual(inventario.stock, 10)
        movimiento = Movimiento.objects.get(producto=producto)
        self.assertEqual(movimiento.importe, 3000)
        self.assertEqual(movimiento.usuario, self.admin)

    def test_venta_confirmada_descuenta_stock(self):
        categoria = CategoriaProducto.objects.create(gym=self.gym, nombre='Bebidas')
        producto = Producto.objects.create(
            gym=self.gym, categoria=categoria, codigo='P002',
            nombre='Agua', precio_compra=5, precio_venta=15,
        )
        InventarioSucursal.objects.create(
            producto=producto, sucursal=self.sucursal, stock=20
        )
        venta = Venta.objects.create(
            gym=self.gym, sucursal=self.sucursal, usuario=self.admin, descuento=10
        )
        VentaDetalle.objects.create(venta=venta, producto=producto, cantidad=3, precio=15)

        ok, _ = venta.confirmar()
        self.assertTrue(ok)

        venta.refresh_from_db()
        self.assertEqual(venta.estado, Venta.CONFIRMADA)
        self.assertEqual(venta.subtotal, 45)
        self.assertEqual(venta.total, 35)
        inventario = InventarioSucursal.objects.get(producto=producto, sucursal=self.sucursal)
        self.assertEqual(inventario.stock, 17)

    def test_venta_sin_stock_no_se_confirma(self):
        categoria = CategoriaProducto.objects.create(gym=self.gym, nombre='Ropa')
        producto = Producto.objects.create(
            gym=self.gym, categoria=categoria, codigo='P003',
            nombre='Playera', precio_compra=100, precio_venta=200,
        )
        venta = Venta.objects.create(
            gym=self.gym, sucursal=self.sucursal, usuario=self.admin
        )
        VentaDetalle.objects.create(venta=venta, producto=producto, cantidad=2, precio=200)

        ok, _ = venta.confirmar()
        self.assertFalse(ok)

        venta.refresh_from_db()
        self.assertEqual(venta.estado, Venta.BORRADOR)

    def test_soft_delete_no_borra_el_registro(self):
        cliente = Cliente.objects.create(
            gym=self.gym, sucursal=self.sucursal, nombre='Baja Logica'
        )
        self.client.post(reverse('clientes:cliente_delete', args=[cliente.pk]))
        cliente.refresh_from_db()
        self.assertFalse(cliente.activo)

    def test_no_se_mezclan_los_datos_entre_gimnasios(self):
        listado = self.client.get(reverse('clientes:cliente_list'))
        self.assertNotContains(listado, 'Cliente Ajeno')

        detalle = self.client.get(
            reverse('clientes:cliente_detail', args=[self.otro_cliente.pk])
        )
        self.assertEqual(detalle.status_code, 404)

    def test_limite_de_sucursales_del_plan(self):
        plan_basico = Plan.objects.get(nombre='Basico')  # 1 sucursal
        self.gym.plan = plan_basico
        self.gym.save()

        self.client.post(
            reverse('core:sucursal_create'), {'nombre': 'Norte', 'direccion': ''}
        )
        self.assertEqual(self.gym.sucursales.filter(activo=True).count(), 1)
