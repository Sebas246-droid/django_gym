"""
Multi-sucursal: que cada sede vea lo suyo y nadie cobre en la equivocada.

Un gimnasio de una sola sucursal no debe notar nada de esto; por eso varias
pruebas comprueban justamente que con una sede la pantalla se ve igual que
antes.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from clientes.models import Asistencia, Cliente, ClienteMembresia, Membresia
from core.models import Gym, Plan, Sucursal
from core.roles import ADMINISTRADOR
from inventario.models import CategoriaProducto, InventarioSucursal, Producto
from ventas.models import Venta, VentaDetalle

User = get_user_model()


class DosSucursalesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('init_saas')
        cls.gym = Gym.objects.create(
            nombre='Dos Sedes', plan=Plan.objects.get(nombre='Premium')
        )
        cls.centro = Sucursal.objects.get(gym=cls.gym)
        cls.centro.nombre = 'Centro'
        cls.centro.save()
        cls.norte = Sucursal.objects.create(gym=cls.gym, nombre='Norte')

        rol = Group.objects.get(name=ADMINISTRADOR)
        for nombre, sede in [('ana', cls.centro), ('beto', cls.norte)]:
            u = User.objects.create_user(
                username=nombre, password='x', gym=cls.gym, sucursal=sede
            )
            u.groups.add(rol)
            setattr(cls, nombre, u)

        cls.categoria = CategoriaProducto.objects.create(
            gym=cls.gym, nombre='Suplementos'
        )
        cls.producto = Producto.objects.create(
            gym=cls.gym, categoria=cls.categoria, nombre='Proteina', codigo='P1',
            precio_compra=100, precio_venta=200,
        )
        for sede in (cls.centro, cls.norte):
            InventarioSucursal.objects.create(
                producto=cls.producto, sucursal=sede, stock=20
            )
        cls.membresia = Membresia.objects.create(
            gym=cls.gym, nombre='Mensual', precio=600, duracion_dias=30
        )

    def vender(self, user, metodo='efectivo'):
        self.client.force_login(user)
        self.client.post(reverse('ventas:pos_agregar', args=[self.producto.pk]))
        self.client.post(reverse('ventas:pos_cobrar'), {'metodo_pago': metodo})

    # --- Corte de caja ----------------------------------------------------

    def test_el_corte_abre_en_la_sede_de_quien_mira(self):
        """El cajon que se cuenta es el de una caja, no la suma del gimnasio."""
        self.vender(self.ana)
        self.vender(self.beto)

        self.client.force_login(self.beto)
        ctx = self.client.get(reverse('ventas:venta_list')).context

        self.assertEqual(ctx['sucursal_vista'], self.norte)
        self.assertEqual(ctx['total_dia'], 200)
        self.assertEqual(ctx['tickets'], 1)
        self.assertEqual([v.sucursal for v in ctx['ventas']], [self.norte])

    def test_el_dueno_puede_ver_todas_juntas(self):
        self.vender(self.ana)
        self.vender(self.beto)

        self.client.force_login(self.ana)
        ctx = self.client.get(
            reverse('ventas:venta_list'), {'sucursal': 'todas'}
        ).context

        self.assertIsNone(ctx['sucursal_vista'])
        self.assertEqual(ctx['total_dia'], 400)
        self.assertEqual(ctx['tickets'], 2)

    def test_se_puede_mirar_el_corte_de_la_otra_sede(self):
        self.vender(self.beto)

        self.client.force_login(self.ana)
        ctx = self.client.get(
            reverse('ventas:venta_list'), {'sucursal': self.norte.pk}
        ).context

        self.assertEqual(ctx['sucursal_vista'], self.norte)
        self.assertEqual(ctx['total_dia'], 200)

    def test_el_desglose_por_metodo_tambien_se_acota_a_la_sede(self):
        self.vender(self.ana, 'efectivo')
        self.vender(self.ana, 'efectivo')
        self.vender(self.beto, 'efectivo')

        self.client.force_login(self.ana)
        ctx = self.client.get(reverse('ventas:venta_list')).context

        self.assertEqual(dict(ctx['metodos'])['Efectivo'], 400)
        self.assertEqual(sum(i for _, i in ctx['metodos']), ctx['total_dia'])

    def test_una_sucursal_ajena_en_la_url_no_saca_datos_de_otro_gym(self):
        otro = Gym.objects.create(nombre='Ajeno', plan=Plan.objects.get(nombre='Basico'))
        ajena = Sucursal.objects.get(gym=otro)

        self.client.force_login(self.ana)
        ctx = self.client.get(
            reverse('ventas:venta_list'), {'sucursal': ajena.pk}
        ).context

        # Cae a la sede propia, no a la ajena
        self.assertEqual(ctx['sucursal_vista'], self.centro)

    # --- Venta de membresia -----------------------------------------------

    def test_la_venta_de_membresia_guarda_donde_se_cobro(self):
        socio = Cliente.objects.create(
            gym=self.gym, sucursal=self.centro, nombre='Socio'
        )
        self.client.force_login(self.beto)

        self.client.post(reverse('clientes:clientemembresia_create'), {
            'cliente': str(socio.pk),
            'membresia': self.membresia.pk,
            'inicio': '2026-08-09',
            'metodo_pago': 'efectivo',
            'precio': '600',
            'descuento': '',
            'observaciones': '',
        })

        venta = ClienteMembresia.objects.get()
        self.assertEqual(venta.sucursal, self.norte)

    def test_mover_de_sede_a_quien_cobro_no_reescribe_el_historico(self):
        socio = Cliente.objects.create(
            gym=self.gym, sucursal=self.centro, nombre='Socio'
        )
        self.client.force_login(self.beto)
        self.client.post(reverse('clientes:clientemembresia_create'), {
            'cliente': str(socio.pk), 'membresia': self.membresia.pk,
            'inicio': '2026-08-09', 'metodo_pago': 'efectivo',
            'precio': '600', 'descuento': '', 'observaciones': '',
        })

        self.beto.sucursal = self.centro
        self.beto.save()

        self.assertEqual(ClienteMembresia.objects.get().sucursal, self.norte)

    def test_la_membresia_cobrada_en_caja_hereda_la_sede_de_la_venta(self):
        """
        No hay pantalla que arme estas lineas, pero el modelo las sostiene: la
        sede tiene que salir de la venta, no del usuario que la confirma.
        """
        socio = Cliente.objects.create(
            gym=self.gym, sucursal=self.centro, nombre='Socio'
        )
        venta = Venta.objects.create(
            gym=self.gym, sucursal=self.norte, usuario=self.ana, cliente=socio
        )
        VentaDetalle.objects.create(
            venta=venta, membresia=self.membresia, cantidad=1, precio=600
        )
        venta.recalcular_total()

        ok, _ = venta.confirmar()

        self.assertTrue(ok)
        # La venta es de Norte aunque la confirme ana, que es de Centro.
        self.assertEqual(ClienteMembresia.objects.get().sucursal, self.norte)

    # --- Tablero ------------------------------------------------------------

    def test_el_tablero_abre_con_el_gimnasio_completo(self):
        self.vender(self.ana)
        self.vender(self.beto)

        self.client.force_login(self.beto)
        ctx = self.client.get(reverse('core:dashboard')).context

        self.assertIsNone(ctx['sucursal_vista'])
        self.assertEqual(ctx['ingresos_hoy'], 400)

    def test_el_tablero_se_puede_acotar_a_una_sede(self):
        self.vender(self.ana)
        self.vender(self.beto)
        Asistencia.objects.create(
            gym=self.gym, sucursal=self.norte,
            cliente=Cliente.objects.create(
                gym=self.gym, sucursal=self.norte, nombre='Del Norte'
            ),
        )

        self.client.force_login(self.ana)
        ctx = self.client.get(
            reverse('core:dashboard'), {'sucursal': self.norte.pk}
        ).context

        self.assertEqual(ctx['sucursal_vista'], self.norte)
        self.assertEqual(ctx['ingresos_hoy'], 200)
        self.assertEqual(ctx['ventas_hoy'], 1)
        self.assertEqual(ctx['asistencias_hoy'], 1)

    def test_la_cartera_se_corta_por_la_sede_del_socio(self):
        Cliente.objects.create(gym=self.gym, sucursal=self.centro, nombre='De Centro')
        Cliente.objects.create(gym=self.gym, sucursal=self.norte, nombre='De Norte')

        self.client.force_login(self.ana)
        ctx = self.client.get(
            reverse('core:dashboard'), {'sucursal': self.centro.pk}
        ).context

        self.assertEqual(ctx['clientes_total'], 1)

    # --- Asignacion de gente -----------------------------------------------

    def test_no_se_puede_dejar_a_un_usuario_sin_sucursal_al_editarlo(self):
        self.client.force_login(self.ana)

        respuesta = self.client.post(
            reverse('accounts:usuario_update', args=[self.beto.pk]),
            {
                'username': 'beto', 'first_name': '', 'last_name': '',
                'email': '', 'telefono': '', 'sucursal': '',
                'rol': Group.objects.get(name=ADMINISTRADOR).pk, 'is_active': 'on',
            },
        )

        self.assertEqual(respuesta.status_code, 200)  # se queda en el formulario
        self.beto.refresh_from_db()
        self.assertEqual(self.beto.sucursal, self.norte)

    def test_no_se_da_de_baja_una_sucursal_con_gente_dentro(self):
        self.client.force_login(self.ana)

        self.client.post(reverse('core:sucursal_delete', args=[self.norte.pk]))

        self.norte.refresh_from_db()
        self.assertTrue(self.norte.activo, 'beto sigue asignado ahi')

    def test_se_da_de_baja_cuando_ya_no_queda_nadie(self):
        self.beto.sucursal = self.centro
        self.beto.save()
        self.client.force_login(self.ana)

        self.client.post(reverse('core:sucursal_delete', args=[self.norte.pk]))

        self.norte.refresh_from_db()
        self.assertFalse(self.norte.activo)

    def test_no_se_puede_quedar_sin_ninguna_sucursal(self):
        self.beto.sucursal = self.centro
        self.beto.save()
        self.client.force_login(self.ana)
        self.client.post(reverse('core:sucursal_delete', args=[self.norte.pk]))

        self.ana.sucursal = None
        self.ana.save()
        self.client.post(reverse('core:sucursal_delete', args=[self.centro.pk]))

        self.centro.refresh_from_db()
        self.assertTrue(self.centro.activo)

    # --- Sede prestada ------------------------------------------------------

    def test_sin_sucursal_asignada_el_pos_avisa(self):
        libre = User.objects.create_user(
            username='libre', password='x', gym=self.gym, sucursal=None
        )
        libre.groups.add(Group.objects.get(name=ADMINISTRADOR))
        self.client.force_login(libre)

        respuesta = self.client.get(reverse('ventas:pos'))

        avisos = [m.message for m in respuesta.context['messages']]
        self.assertTrue(
            any('No tienes sucursal asignada' in a for a in avisos), avisos
        )

    def test_una_sucursal_dada_de_baja_no_se_usa_para_cobrar(self):
        """
        Se apaga la sede por debajo, como quedo en las bases de antes de que
        la baja empezara a exigir mover a la gente.
        """
        Sucursal.objects.filter(pk=self.norte.pk).update(activo=False)
        self.client.force_login(self.beto)

        ctx = self.client.get(reverse('ventas:pos')).context

        self.assertEqual(ctx['sucursal'], self.centro)
        avisos = [m.message for m in ctx['messages']]
        self.assertTrue(any('dada de baja' in a for a in avisos), avisos)


class UnaSolaSucursalTest(TestCase):
    """Lo de arriba no debe cambiarle nada al gimnasio de un solo local."""

    @classmethod
    def setUpTestData(cls):
        call_command('init_saas')
        cls.gym = Gym.objects.create(
            nombre='Un Local', plan=Plan.objects.get(nombre='Basico')
        )
        cls.sucursal = Sucursal.objects.get(gym=cls.gym)
        cls.user = User.objects.create_user(
            username='dueno', password='x', gym=cls.gym, sucursal=cls.sucursal
        )
        cls.user.groups.add(Group.objects.get(name=ADMINISTRADOR))

    def setUp(self):
        self.client.force_login(self.user)

    def test_no_se_ofrece_selector_de_sede(self):
        self.assertFalse(
            self.client.get(reverse('core:dashboard')).context['varias_sucursales']
        )
        self.assertFalse(
            self.client.get(reverse('ventas:venta_list')).context['varias_sucursales']
        )

    def test_el_tablero_y_el_corte_siguen_abriendo(self):
        self.assertEqual(self.client.get(reverse('core:dashboard')).status_code, 200)
        self.assertEqual(self.client.get(reverse('ventas:venta_list')).status_code, 200)

    def test_sin_sucursal_asignada_no_se_le_avisa_nada(self):
        """Con una sola sede no hay nada que confundir: el aviso seria ruido."""
        self.user.sucursal = None
        self.user.save()

        respuesta = self.client.get(reverse('ventas:pos'))

        self.assertEqual(
            [m.message for m in respuesta.context['messages']], []
        )
