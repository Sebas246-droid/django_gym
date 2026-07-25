"""Pruebas del punto de venta."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from clientes.models import Cliente
from core.models import Gym, Plan, Sucursal
from core.roles import RECEPCION
from inventario.models import CategoriaProducto, InventarioSucursal, Producto
from ventas.models import Venta

User = get_user_model()


class PuntoDeVentaTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('init_saas')
        cls.gym = Gym.objects.create(
            nombre='Iron House', plan=Plan.objects.get(nombre='Pro')
        )
        cls.sucursal = Sucursal.objects.get(gym=cls.gym, nombre='Principal')
        cls.cajero = User.objects.create_user(
            username='caja', password='pass12345',
            gym=cls.gym, sucursal=cls.sucursal,
        )
        cls.cajero.groups.add(Group.objects.get(name=RECEPCION))

        cls.categoria = CategoriaProducto.objects.create(
            gym=cls.gym, nombre='Suplementos'
        )
        cls.producto = Producto.objects.create(
            gym=cls.gym, categoria=cls.categoria, codigo='P1',
            nombre='Proteina', precio_compra=300, precio_venta=500,
        )
        InventarioSucursal.objects.create(
            producto=cls.producto, sucursal=cls.sucursal, stock=10
        )

    def setUp(self):
        self.client.force_login(self.cajero)

    def agregar(self, producto=None):
        return self.client.post(
            reverse('ventas:pos_agregar', args=[(producto or self.producto).pk])
        )

    def carrito(self):
        return Venta.objects.filter(
            gym=self.gym, usuario=self.cajero, estado=Venta.BORRADOR, activo=True
        ).first()

    # --- Catalogo ---------------------------------------------------------

    def test_abrir_la_caja_no_crea_carritos_vacios(self):
        respuesta = self.client.get(reverse('ventas:pos'))

        self.assertEqual(respuesta.status_code, 200)
        self.assertIsNone(respuesta.context['venta'])
        self.assertEqual(Venta.objects.count(), 0)

    def test_las_tarjetas_traen_el_stock_de_la_sucursal(self):
        respuesta = self.client.get(reverse('ventas:pos'))

        producto = respuesta.context['productos'][0]
        self.assertEqual(producto.stock_actual, 10)

    def test_solo_muestra_productos_del_propio_gimnasio(self):
        otro_gym = Gym.objects.create(
            nombre='Otro', plan=Plan.objects.get(nombre='Basico')
        )
        Producto.objects.create(
            gym=otro_gym,
            categoria=CategoriaProducto.objects.create(gym=otro_gym, nombre='X'),
            codigo='P1', nombre='Ajeno', precio_venta=100,
        )

        respuesta = self.client.get(reverse('ventas:pos'))

        self.assertNotContains(respuesta, 'Ajeno')

    def test_la_busqueda_filtra(self):
        respuesta = self.client.get(reverse('ventas:pos'), {'q': 'zzz'})

        self.assertEqual(len(respuesta.context['productos']), 0)

    # --- Carrito ----------------------------------------------------------

    def test_agregar_crea_el_carrito_con_el_precio_de_venta(self):
        self.agregar()

        venta = self.carrito()
        linea = venta.detalles.get()
        self.assertEqual(linea.cantidad, 1)
        self.assertEqual(linea.precio, self.producto.precio_venta)
        self.assertEqual(venta.total, 500)

    def test_agregar_dos_veces_suma_cantidad_sin_duplicar_la_linea(self):
        self.agregar()
        self.agregar()

        venta = self.carrito()
        self.assertEqual(venta.detalles.count(), 1)
        self.assertEqual(venta.detalles.get().cantidad, 2)
        self.assertEqual(venta.total, 1000)

    def test_el_carrito_es_de_cada_cajero(self):
        self.agregar()
        otro = User.objects.create_user(
            username='caja2', password='pass12345',
            gym=self.gym, sucursal=self.sucursal,
        )
        otro.groups.add(Group.objects.get(name=RECEPCION))

        self.client.force_login(otro)
        respuesta = self.client.get(reverse('ventas:pos'))

        self.assertIsNone(respuesta.context['venta'])

    def test_menos_baja_la_cantidad_y_en_uno_quita_la_linea(self):
        self.agregar()
        self.agregar()
        linea = self.carrito().detalles.get()

        self.client.post(reverse('ventas:pos_linea', args=[linea.pk]), {'accion': 'menos'})
        self.assertEqual(self.carrito().detalles.get().cantidad, 1)

        self.client.post(reverse('ventas:pos_linea', args=[linea.pk]), {'accion': 'menos'})
        self.assertEqual(self.carrito().detalles.count(), 0)

    def test_vaciar_deja_la_caja_lista_para_el_siguiente(self):
        self.agregar()

        self.client.post(reverse('ventas:pos_cancelar'))

        self.assertIsNone(self.carrito())

    # --- Cobro ------------------------------------------------------------

    def test_cobrar_confirma_la_venta_y_descuenta_stock(self):
        self.agregar()
        self.agregar()

        respuesta = self.client.post(
            reverse('ventas:pos_cobrar'),
            {'metodo_pago': 'tarjeta', 'descuento': '100', 'cliente': ''},
        )

        venta = Venta.objects.get()
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(venta.estado, Venta.CONFIRMADA)
        self.assertEqual(venta.subtotal, 1000)
        self.assertEqual(venta.total, 900)
        self.assertEqual(venta.metodo_pago, 'tarjeta')
        self.assertEqual(self.producto.stock_en(self.sucursal), 8)

    def test_cobrar_deja_el_carrito_limpio(self):
        self.agregar()
        self.client.post(reverse('ventas:pos_cobrar'), {'metodo_pago': 'efectivo'})

        self.assertIsNone(self.carrito())

    def test_cobrar_con_cliente_lo_deja_en_la_venta(self):
        cliente = Cliente.objects.create(
            gym=self.gym, sucursal=self.sucursal, nombre='Ana Torres'
        )
        self.agregar()

        self.client.post(
            reverse('ventas:pos_cobrar'),
            {'metodo_pago': 'efectivo', 'cliente': cliente.pk},
        )

        self.assertEqual(Venta.objects.get().cliente, cliente)

    def test_no_se_cobra_sin_stock_suficiente(self):
        InventarioSucursal.objects.filter(producto=self.producto).update(stock=1)
        self.agregar()
        self.agregar()

        self.client.post(reverse('ventas:pos_cobrar'), {'metodo_pago': 'efectivo'})

        self.assertEqual(self.carrito().estado, Venta.BORRADOR)
        self.assertEqual(self.producto.stock_en(self.sucursal), 1)

    def test_el_carrito_vacio_no_se_cobra(self):
        respuesta = self.client.post(
            reverse('ventas:pos_cobrar'), {'metodo_pago': 'efectivo'}
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Venta.objects.filter(estado=Venta.CONFIRMADA).count(), 0)

    def test_un_descuento_absurdo_no_deja_el_total_negativo(self):
        self.agregar()

        self.client.post(
            reverse('ventas:pos_cobrar'),
            {'metodo_pago': 'efectivo', 'descuento': '99999'},
        )

        self.assertEqual(Venta.objects.get().total, 0)

    def test_un_descuento_con_basura_se_toma_como_cero(self):
        self.agregar()

        self.client.post(
            reverse('ventas:pos_cobrar'),
            {'metodo_pago': 'efectivo', 'descuento': 'abc'},
        )

        self.assertEqual(Venta.objects.get().total, 500)
