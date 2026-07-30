"""Pruebas del inventario: la pantalla unica y el libro de movimientos."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from core.models import Gym, Plan, Sucursal
from core.roles import ADMINISTRADOR
from inventario.models import (
    CategoriaProducto,
    InventarioSucursal,
    Movimiento,
    Producto,
)

User = get_user_model()


class BaseInventarioTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('init_saas')
        cls.gym = Gym.objects.create(
            nombre='Iron House', plan=Plan.objects.get(nombre='Pro')
        )
        cls.sucursal = Sucursal.objects.get(gym=cls.gym, nombre='Principal')
        cls.usuario = User.objects.create_user(
            username='admin', password='pass12345',
            gym=cls.gym, sucursal=cls.sucursal,
        )
        cls.usuario.groups.add(Group.objects.get(name=ADMINISTRADOR))
        cls.categoria = CategoriaProducto.objects.create(
            gym=cls.gym, nombre='Suplementos'
        )
        cls.producto = Producto.objects.create(
            gym=cls.gym, categoria=cls.categoria, codigo='P1',
            nombre='Proteina', precio_compra=300, precio_venta=500,
        )

    def setUp(self):
        self.client.force_login(self.usuario)


class MovimientoTest(BaseInventarioTest):
    """
    Todo cambio de existencias deja su renglon. Antes las entradas eran compras
    con cabecera y las salidas no se anotaban en ningun lado, asi que no habia
    forma de responder por que hay lo que hay.
    """

    def url(self):
        return reverse('inventario:movimiento_create')

    def mover(self, **extra):
        datos = {
            'producto': self.producto.pk, 'sucursal': self.sucursal.pk,
            'tipo': 'entrada', 'motivo': 'compra', 'cantidad': '10',
        }
        return self.client.post(self.url(), {**datos, **extra})

    def test_una_entrada_sube_el_stock_y_deja_su_renglon(self):
        self.mover()

        self.assertEqual(self.producto.stock_en(self.sucursal), 10)
        movimiento = Movimiento.objects.get()
        self.assertEqual(movimiento.tipo, Movimiento.ENTRADA)
        self.assertEqual(movimiento.motivo, Movimiento.COMPRA)
        self.assertEqual(movimiento.usuario, self.usuario)

    def test_una_merma_baja_el_stock(self):
        self.mover()
        self.mover(tipo='salida', motivo='merma', cantidad='3', nota='Se caduco')

        self.assertEqual(self.producto.stock_en(self.sucursal), 7)
        merma = Movimiento.objects.get(motivo=Movimiento.MERMA)
        self.assertEqual(merma.nota, 'Se caduco')

    def test_no_se_puede_sacar_mas_de_lo_que_hay(self):
        self.mover(cantidad='5')

        respuesta = self.mover(tipo='salida', motivo='merma', cantidad='9')

        self.assertContains(respuesta, 'Solo hay 5')
        self.assertEqual(self.producto.stock_en(self.sucursal), 5)

    def test_una_merma_no_puede_ser_entrada(self):
        respuesta = self.mover(tipo='entrada', motivo='merma')

        self.assertContains(respuesta, 'no aplica')
        self.assertFalse(Movimiento.objects.exists())

    def test_la_venta_no_se_captura_a_mano(self):
        """La anota el punto de venta al cobrar; a mano se contaria dos veces."""
        respuesta = self.mover(tipo='salida', motivo='venta', cantidad='1')

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Movimiento.objects.exists())

    def test_sin_importe_toma_el_del_producto(self):
        self.mover()
        self.assertEqual(Movimiento.objects.get().precio, 300)

    def test_una_salida_sin_importe_toma_el_precio_de_venta(self):
        self.mover()
        self.mover(tipo='salida', motivo='merma', cantidad='2')

        merma = Movimiento.objects.get(motivo=Movimiento.MERMA)
        self.assertEqual(merma.precio, 500)

    def test_una_compra_mas_cara_actualiza_el_costo(self):
        self.mover(precio='350')

        self.producto.refresh_from_db()
        self.assertEqual(self.producto.precio_compra, 350)

    def test_una_merma_no_toca_el_costo(self):
        """El costo lo fija lo que se paga al comprar, no lo que se tira."""
        self.mover()
        self.mover(tipo='salida', motivo='merma', cantidad='2', precio='999')

        self.producto.refresh_from_db()
        self.assertEqual(self.producto.precio_compra, 300)

    def test_no_se_mueve_un_producto_de_otro_gimnasio(self):
        otro = Gym.objects.create(nombre='Otro', plan=Plan.objects.get(nombre='Basico'))
        ajeno = Producto.objects.create(
            gym=otro,
            categoria=CategoriaProducto.objects.create(gym=otro, nombre='X'),
            codigo='P1', nombre='Ajeno', precio_venta=100,
        )

        respuesta = self.mover(producto=ajeno.pk)

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Movimiento.objects.exists())

    def test_el_libro_solo_muestra_lo_del_propio_gimnasio(self):
        self.mover()
        otro = Gym.objects.create(nombre='Otro', plan=Plan.objects.get(nombre='Basico'))
        Movimiento.objects.create(
            gym=otro,
            producto=Producto.objects.create(
                gym=otro,
                categoria=CategoriaProducto.objects.create(gym=otro, nombre='X'),
                codigo='Z9', nombre='Ajeno', precio_venta=1,
            ),
            sucursal=Sucursal.objects.get(gym=otro),
            tipo='entrada', motivo='compra', cantidad=5,
        )

        respuesta = self.client.get(reverse('inventario:movimiento_list'))

        self.assertEqual(len(respuesta.context['movimientos']), 1)


class VentaDejaSuSalidaTest(BaseInventarioTest):
    """Cobrar en la caja tiene que aparecer en el libro como cualquier salida."""

    def test_la_venta_confirmada_anota_su_movimiento(self):
        from ventas.models import Venta, VentaDetalle

        Movimiento.registrar(
            producto=self.producto, sucursal=self.sucursal,
            tipo=Movimiento.ENTRADA, motivo=Movimiento.COMPRA, cantidad=10,
        )
        venta = Venta.objects.create(
            gym=self.gym, sucursal=self.sucursal, usuario=self.usuario
        )
        detalle = VentaDetalle.objects.create(
            venta=venta, producto=self.producto, cantidad=3, precio=500
        )
        venta.recalcular_total()

        ok, _ = venta.confirmar()

        self.assertTrue(ok)
        self.assertEqual(self.producto.stock_en(self.sucursal), 7)
        salida = Movimiento.objects.get(motivo=Movimiento.VENTA)
        self.assertEqual(salida.cantidad, 3)
        self.assertEqual(salida.venta_detalle, detalle)


class PantallaDeInventarioTest(BaseInventarioTest):
    def test_el_producto_sale_con_sus_existencias(self):
        InventarioSucursal.objects.create(
            producto=self.producto, sucursal=self.sucursal, stock=7
        )
        respuesta = self.client.get(reverse('inventario:producto_list'))

        producto = respuesta.context['productos'][0]
        self.assertEqual(producto.inventario.stock, 7)

    def test_sin_movimientos_todavia_se_ve_en_cero(self):
        respuesta = self.client.get(reverse('inventario:producto_list'))

        self.assertIsNone(respuesta.context['productos'][0].inventario)
        self.assertContains(respuesta, 'Movimiento')

    def test_muestra_el_stock_de_la_sucursal_que_se_pide(self):
        otra = Sucursal.objects.create(gym=self.gym, nombre='Norte')
        InventarioSucursal.objects.create(
            producto=self.producto, sucursal=self.sucursal, stock=7
        )
        InventarioSucursal.objects.create(
            producto=self.producto, sucursal=otra, stock=2
        )

        respuesta = self.client.get(
            reverse('inventario:producto_list'), {'sucursal': otra.pk}
        )

        self.assertEqual(respuesta.context['sucursal'], otra)
        self.assertEqual(respuesta.context['productos'][0].inventario.stock, 2)

    def test_no_se_cuela_el_stock_de_otro_gimnasio(self):
        otro = Gym.objects.create(nombre='Otro', plan=Plan.objects.get(nombre='Basico'))
        ajena = Sucursal.objects.get(gym=otro)

        respuesta = self.client.get(
            reverse('inventario:producto_list'), {'sucursal': ajena.pk}
        )

        # Una sucursal de otro gym no se elige: se cae a la propia.
        self.assertEqual(respuesta.context['sucursal'], self.sucursal)


class CodigoRepetidoTest(BaseInventarioTest):
    def test_dice_a_donde_ir_cuando_el_producto_ya_existe(self):
        """Casi siempre no es un error de captura: llego mas de lo mismo."""
        respuesta = self.client.post(reverse('inventario:producto_create'), {
            'codigo': self.producto.codigo, 'nombre': 'Otra proteina',
            'categoria': str(self.categoria.pk),
            'precio_compra': '300', 'precio_venta': '500', 'cantidad': '0',
        })

        cuerpo = respuesta.content.decode()
        self.assertIn('Ya tienes', cuerpo)
        self.assertIn(reverse('inventario:movimiento_create'), cuerpo)
        self.assertEqual(Producto.objects.filter(gym=self.gym).count(), 1)


class AltaConExistenciasTest(BaseInventarioTest):
    def test_el_alta_con_cantidad_deja_su_movimiento(self):
        self.client.post(reverse('inventario:producto_create'), {
            'codigo': 'NUEVO', 'nombre': 'Creatina',
            'categoria': str(self.categoria.pk),
            'precio_compra': '200', 'precio_venta': '400',
            'cantidad': '8', 'sucursal': self.sucursal.pk,
        })

        nuevo = Producto.objects.get(gym=self.gym, codigo='NUEVO')
        self.assertEqual(nuevo.stock_en(self.sucursal), 8)
        movimiento = Movimiento.objects.get(producto=nuevo)
        self.assertEqual(movimiento.motivo, Movimiento.COMPRA)
        self.assertEqual(movimiento.nota, 'Existencias iniciales')
