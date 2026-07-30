"""Pruebas del inventario: la pantalla unica y la entrada de mercancia."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from core.models import Gym, Plan, Sucursal
from core.roles import ADMINISTRADOR
from inventario.models import (
    CategoriaProducto,
    Compra,
    InventarioSucursal,
    Producto,
    Proveedor,
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


class EntradaDeMercanciaTest(BaseInventarioTest):
    """
    Reabastecer costaba cuatro pasos por la pantalla de compras, asi que nadie
    la usaba y el stock se corregia a mano, sin rastro del costo. Ahora es uno.
    """

    def url(self):
        return reverse('inventario:producto_entrada', args=[self.producto.pk])

    def entrar(self, **extra):
        return self.client.post(
            self.url(), {'cantidad': '12', 'sucursal': self.sucursal.pk, **extra}
        )

    def test_sube_el_stock(self):
        self.entrar()
        self.assertEqual(self.producto.stock_en(self.sucursal), 12)

    def test_queda_asentada_como_compra_confirmada(self):
        self.entrar()

        compra = Compra.objects.get(gym=self.gym)
        self.assertEqual(compra.estado, Compra.CONFIRMADA)
        self.assertEqual(compra.usuario, self.usuario)
        detalle = compra.detalles.get()
        self.assertEqual(detalle.producto, self.producto)
        self.assertEqual(detalle.cantidad, 12)

    def test_sin_costo_toma_el_del_producto(self):
        self.entrar()
        self.assertEqual(Compra.objects.get().detalles.get().precio, 300)
        self.assertEqual(Compra.objects.get().total, 3600)

    def test_un_costo_distinto_manda(self):
        """Si el proveedor subio el precio, esa entrada vale lo que costo."""
        self.entrar(precio='350')
        self.assertEqual(Compra.objects.get().detalles.get().precio, 350)

    def test_dos_entradas_se_acumulan(self):
        self.entrar()
        self.entrar(cantidad='5')
        self.assertEqual(self.producto.stock_en(self.sucursal), 17)
        self.assertEqual(Compra.objects.filter(gym=self.gym).count(), 2)

    def test_el_proveedor_es_opcional(self):
        proveedor = Proveedor.objects.create(gym=self.gym, nombre='Nutrimex')
        self.entrar(proveedor=proveedor.pk)
        self.assertEqual(Compra.objects.get().proveedor, proveedor)

    def test_cantidad_cero_no_pasa(self):
        respuesta = self.entrar(cantidad='0')
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Compra.objects.exists())

    def test_no_se_carga_a_un_producto_de_otro_gimnasio(self):
        otro = Gym.objects.create(nombre='Otro', plan=Plan.objects.get(nombre='Basico'))
        ajeno = Producto.objects.create(
            gym=otro,
            categoria=CategoriaProducto.objects.create(gym=otro, nombre='X'),
            codigo='P1', nombre='Ajeno', precio_venta=100,
        )
        respuesta = self.client.post(
            reverse('inventario:producto_entrada', args=[ajeno.pk]),
            {'cantidad': '5', 'sucursal': self.sucursal.pk},
        )
        self.assertEqual(respuesta.status_code, 404)


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
        self.assertContains(respuesta, 'Entrada')

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


class CostoDelProductoTest(BaseInventarioTest):
    """
    Al mismo producto se le compra a varios proveedores y a distinto costo. El
    costo del producto tiene que seguir al de la ultima compra: es el que
    decide el margen y el que se propone en la siguiente entrada.
    """

    def entrar(self, precio=None, proveedor=None):
        datos = {'cantidad': '10', 'sucursal': self.sucursal.pk}
        if precio is not None:
            datos['precio'] = precio
        if proveedor is not None:
            datos['proveedor'] = proveedor.pk
        return self.client.post(
            reverse('inventario:producto_entrada', args=[self.producto.pk]), datos
        )

    def test_una_entrada_mas_cara_actualiza_el_costo(self):
        self.entrar(precio='350')

        self.producto.refresh_from_db()
        self.assertEqual(self.producto.precio_compra, 350)

    def test_sin_costo_no_lo_mueve(self):
        self.entrar()

        self.producto.refresh_from_db()
        self.assertEqual(self.producto.precio_compra, 300)

    def test_dos_proveedores_distintos_quedan_por_separado(self):
        uno = Proveedor.objects.create(gym=self.gym, nombre='Nutrimex')
        otro = Proveedor.objects.create(gym=self.gym, nombre='Suplenorte')

        self.entrar(precio='300', proveedor=uno)
        self.entrar(precio='340', proveedor=otro)

        compras = Compra.objects.filter(gym=self.gym).order_by('pk')
        self.assertEqual(
            [(c.proveedor.nombre, c.detalles.get().precio) for c in compras],
            [('Nutrimex', 300), ('Suplenorte', 340)],
        )
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.precio_compra, 340)
        self.assertEqual(self.producto.stock_en(self.sucursal), 20)

    def test_la_pantalla_muestra_a_quien_se_le_compro(self):
        proveedor = Proveedor.objects.create(gym=self.gym, nombre='Nutrimex')
        self.entrar(precio='320', proveedor=proveedor)

        respuesta = self.client.get(
            reverse('inventario:producto_entrada', args=[self.producto.pk])
        )

        self.assertContains(respuesta, 'Nutrimex')
        self.assertContains(respuesta, '320')

    def test_el_costo_nuevo_se_propone_la_siguiente_vez(self):
        self.entrar(precio='350')

        respuesta = self.client.get(
            reverse('inventario:producto_entrada', args=[self.producto.pk])
        )

        self.assertContains(respuesta, 'placeholder="350')


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
        self.assertIn(
            reverse('inventario:producto_entrada', args=[self.producto.pk]), cuerpo
        )
        self.assertEqual(Producto.objects.filter(gym=self.gym).count(), 1)
