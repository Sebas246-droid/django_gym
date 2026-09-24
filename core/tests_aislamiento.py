"""
Que no se cruce informacion entre gimnasios.

Es la propiedad mas importante de un SaaS multi-gimnasio y la mas facil de
romper sin darse cuenta: basta una vista que busque por `pk` y se olvide del
gym. Las pruebas de cada modulo miran que lo propio se vea; esta mira lo
contrario, que es lo que nadie prueba a mano.

El metodo es a lo bruto a proposito: se arma un gimnasio completo, se entra
como administrador de OTRO gimnasio y se pide por url cada objeto del primero.
Ninguna de esas direcciones puede contestar 200.

Cuando se agregue una pantalla con <int:pk>, va en la tabla de abajo.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from clientes.models import Asistencia, Cliente, ClienteMembresia, Huella, Membresia
from core.models import Gym, Plan, Sucursal
from core.roles import ADMINISTRADOR
from entrenamiento.models import Entrenamiento
from inventario.models import CategoriaProducto, InventarioSucursal, Producto
from ventas.models import Venta

User = get_user_model()


class NadaSeCruzaEntreGimnasiosTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('init_saas')
        plan = Plan.objects.get(nombre='Pro')

        # --- El gimnasio ajeno, con una de cada cosa --------------------
        cls.ajeno = Gym.objects.create(nombre='Gimnasio Ajeno', plan=plan)
        sede = Sucursal.objects.get(gym=cls.ajeno)
        cls.sede_ajena = sede

        cls.cliente = Cliente.objects.create(
            gym=cls.ajeno, sucursal=sede, nombre='Socio Ajeno'
        )
        cls.membresia = Membresia.objects.create(
            gym=cls.ajeno, nombre='Mensual', precio=600, duracion_dias=30
        )
        cls.venta_membresia = ClienteMembresia.objects.create(
            gym=cls.ajeno, cliente=cls.cliente, membresia=cls.membresia,
            inicio=timezone.localdate(), precio=600,
        )
        cls.asistencia = Asistencia.objects.create(
            gym=cls.ajeno, sucursal=sede, cliente=cls.cliente
        )
        cls.huella = Huella.objects.create(
            gym=cls.ajeno, cliente=cls.cliente, plantilla=b'x'
        )
        cls.entrenamiento = Entrenamiento.objects.create(
            gym=cls.ajeno, nombre='Funcional'
        )
        cls.categoria = CategoriaProducto.objects.create(
            gym=cls.ajeno, nombre='Suplementos'
        )
        cls.producto = Producto.objects.create(
            gym=cls.ajeno, categoria=cls.categoria, codigo='A1',
            nombre='Proteina', precio_venta=500,
        )
        cls.inventario = InventarioSucursal.objects.get_or_create(
            producto=cls.producto, sucursal=sede
        )[0]
        cls.venta = Venta.objects.create(gym=cls.ajeno, sucursal=sede)
        cls.usuario_ajeno = User.objects.create_user(
            username='ajeno', password='pass12345', gym=cls.ajeno, sucursal=sede
        )
        cls.imagen = cls.ajeno.imagenes.create(imagen='gyms/galeria/x.jpg')

        # --- El mio, desde donde se intenta fisgonear -------------------
        cls.mio = Gym.objects.create(nombre='Mi Gimnasio', plan=plan)
        cls.yo = User.objects.create_user(
            username='yo', password='pass12345',
            gym=cls.mio, sucursal=Sucursal.objects.get(gym=cls.mio),
            is_staff=False,
        )
        cls.yo.groups.add(Group.objects.get(name=ADMINISTRADOR))

    def setUp(self):
        self.client.force_login(self.yo)

    def direcciones(self):
        """Cada pantalla con <int:pk> del panel, apuntando a algo ajeno."""
        return [
            ('clientes:cliente_detail', self.cliente.pk),
            ('clientes:cliente_update', self.cliente.pk),
            ('clientes:cliente_delete', self.cliente.pk),
            ('clientes:cliente_credencial', self.cliente.pk),
            ('clientes:cliente_credencial_imagen', self.cliente.pk),
            ('clientes:membresia_update', self.membresia.pk),
            ('clientes:membresia_delete', self.membresia.pk),
            ('clientes:clientemembresia_update', self.venta_membresia.pk),
            ('clientes:clientemembresia_cancelar', self.venta_membresia.pk),
            ('clientes:huella_enrolar', self.cliente.pk),
            ('clientes:huella_borrar', self.huella.pk),
            ('clientes:asistencia_registrar', self.cliente.pk),
            ('clientes:asistencia_entrenamiento', self.asistencia.pk),
            ('entrenamiento:update', self.entrenamiento.pk),
            ('entrenamiento:delete', self.entrenamiento.pk),
            ('inventario:categoria_update', self.categoria.pk),
            ('inventario:categoria_delete', self.categoria.pk),
            ('inventario:producto_update', self.producto.pk),
            ('inventario:producto_delete', self.producto.pk),
            ('inventario:inventario_update', self.inventario.pk),
            ('ventas:venta_detail', self.venta.pk),
            ('ventas:pos_agregar', self.producto.pk),
            ('accounts:usuario_update', self.usuario_ajeno.pk),
            ('accounts:usuario_toggle', self.usuario_ajeno.pk),
            ('accounts:usuario_password', self.usuario_ajeno.pk),
            ('core:sucursal_update', self.sede_ajena.pk),
            ('core:sucursal_delete', self.sede_ajena.pk),
            ('core:sitio_imagen_delete', self.imagen.pk),
        ]

    def test_ninguna_pantalla_ajena_contesta(self):
        """
        Ni abriendola ni mandandole datos. Un 200 aqui es una fuga: significa
        que la vista encontro el objeto sin preguntar de quien era.
        """
        for nombre, pk in self.direcciones():
            for metodo in ('get', 'post'):
                with self.subTest(pantalla=nombre, metodo=metodo):
                    respuesta = getattr(self.client, metodo)(
                        reverse(nombre, args=[pk])
                    )
                    self.assertNotEqual(
                        respuesta.status_code, 200,
                        f'{nombre} le abrio a un gimnasio que no es su dueno',
                    )

    def test_lo_ajeno_sigue_intacto(self):
        """Que no conteste no basta: tampoco puede haber cambiado nada."""
        for nombre, pk in self.direcciones():
            self.client.post(reverse(nombre, args=[pk]))

        self.cliente.refresh_from_db()
        self.usuario_ajeno.refresh_from_db()
        self.assertTrue(self.cliente.activo)
        self.assertTrue(self.usuario_ajeno.is_active)
        self.assertTrue(Huella.objects.filter(pk=self.huella.pk).exists())
        self.assertTrue(
            Sucursal.objects.get(pk=self.sede_ajena.pk).activo
        )
        self.assertEqual(
            ClienteMembresia.objects.get(pk=self.venta_membresia.pk).estado,
            ClienteMembresia.VIGENTE,
        )
        self.assertTrue(self.ajeno.imagenes.filter(pk=self.imagen.pk).exists())

    def test_las_listas_solo_traen_lo_propio(self):
        """La otra mitad: lo ajeno no se cuela en ninguna lista."""
        pantallas = [
            ('clientes:cliente_list', 'clientes'),
            ('clientes:membresia_list', 'membresias'),
            ('clientes:clientemembresia_list', 'ventas_membresia'),
            ('clientes:asistencia_list', 'asistencias'),
            ('inventario:producto_list', 'productos'),
            ('inventario:categoria_list', 'categorias'),
            ('entrenamiento:list', 'entrenamientos'),
            ('ventas:venta_list', 'ventas'),
            ('accounts:usuario_list', 'usuarios'),
            ('core:sucursal_list', 'sucursales'),
        ]
        for nombre, clave in pantallas:
            with self.subTest(pantalla=nombre):
                lista = self.client.get(reverse(nombre)).context[clave]
                ajenos = [
                    f for f in lista
                    if getattr(f, 'gym_id', self.mio.pk) != self.mio.pk
                ]
                self.assertEqual(ajenos, [], f'{nombre} enseno datos ajenos')

    def test_el_kiosco_no_deja_entrar_a_un_socio_de_otro_gimnasio(self):
        """
        El acceso se pide por numero, y los numeros se repiten entre gimnasios:
        el 1000 existe en todos. Si el kiosco no filtrara por gym, marcaria la
        entrada del socio equivocado.
        """
        respuesta = self.client.post(
            reverse('clientes:checkin'),
            {'numero_usuario': self.cliente.numero_usuario},
            follow=True,
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(
            Asistencia.objects.filter(cliente=self.cliente)
            .exclude(pk=self.asistencia.pk)
            .exists()
        )
