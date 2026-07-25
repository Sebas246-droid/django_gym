"""Pruebas del acceso por numero de usuario y del sitio publico."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from clientes.models import Asistencia, Cliente, ClienteMembresia, Membresia
from core.models import Gym, GymImagen, Plan, Sucursal
from core.roles import ADMINISTRADOR
from entrenamiento.models import Entrenamiento

User = get_user_model()


class BaseGymTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('init_saas')
        cls.gym = Gym.objects.create(
            nombre='Iron House', plan=Plan.objects.get(nombre='Pro')
        )
        cls.sucursal = Sucursal.objects.get(gym=cls.gym, nombre='Principal')
        cls.usuario = User.objects.create_user(
            username='recepcion', password='pass12345',
            gym=cls.gym, sucursal=cls.sucursal,
        )
        cls.usuario.groups.add(Group.objects.get(name=ADMINISTRADOR))
        cls.membresia = Membresia.objects.create(
            gym=cls.gym, nombre='Mensual', precio=600, duracion_dias=30
        )

    def setUp(self):
        self.client.force_login(self.usuario)

    def crear_cliente(self, nombre='Cliente Prueba'):
        return Cliente.objects.create(
            gym=self.gym, sucursal=self.sucursal, nombre=nombre
        )

    def vender_membresia(self, cliente, inicio):
        return ClienteMembresia.objects.create(
            gym=self.gym, cliente=cliente, membresia=self.membresia,
            inicio=inicio, precio=600, usuario=self.usuario,
        )


class NumeroUsuarioTest(BaseGymTest):
    def test_se_asigna_solo_y_es_consecutivo(self):
        primero = self.crear_cliente('Uno')
        segundo = self.crear_cliente('Dos')
        self.assertEqual(primero.numero_usuario, '1000')
        self.assertEqual(segundo.numero_usuario, '1001')
        self.assertEqual(len(primero.numero_usuario), 4)

    def test_cada_gimnasio_lleva_su_propia_numeracion(self):
        otro_gym = Gym.objects.create(
            nombre='Otro', plan=Plan.objects.get(nombre='Basico')
        )
        mio = self.crear_cliente('Mio')
        ajeno = Cliente.objects.create(
            gym=otro_gym,
            sucursal=Sucursal.objects.get(gym=otro_gym),
            nombre='Ajeno',
        )
        self.assertEqual(mio.numero_usuario, ajeno.numero_usuario)


class AccesoPorNumeroTest(BaseGymTest):
    def _ingresar(self, numero):
        self.client.post(reverse('clientes:checkin'), {'numero_usuario': numero})
        return self.client.session.get('acceso')

    def test_membresia_vigente_da_verde_y_registra_entrada(self):
        cliente = self.crear_cliente()
        self.vender_membresia(cliente, timezone.localdate())

        resultado = self._ingresar(cliente.numero_usuario)

        self.assertEqual(resultado['estado'], 'ok')
        self.assertEqual(resultado['nombre'], cliente.nombre)
        self.assertEqual(
            Asistencia.objects.filter(cliente=cliente, tipo='entrada').count(), 1
        )

    def test_membresia_vencida_avisa_en_rojo(self):
        cliente = self.crear_cliente()
        self.vender_membresia(cliente, timezone.localdate() - timedelta(days=60))

        resultado = self._ingresar(cliente.numero_usuario)

        self.assertEqual(resultado['estado'], 'vencida')
        self.assertIn('vencio', resultado['mensaje'])

    def test_sin_membresia_tambien_avisa(self):
        cliente = self.crear_cliente()

        resultado = self._ingresar(cliente.numero_usuario)

        self.assertEqual(resultado['estado'], 'vencida')
        self.assertIn('no tienes una membresia', resultado['mensaje'])

    def test_por_vencer_pide_renovar(self):
        cliente = self.crear_cliente()
        self.vender_membresia(cliente, timezone.localdate() - timedelta(days=28))

        resultado = self._ingresar(cliente.numero_usuario)

        self.assertEqual(resultado['estado'], 'aviso')
        self.assertIn('renovar', resultado['detalle'])

    def test_numero_inexistente_no_registra_nada(self):
        resultado = self._ingresar('9999')

        self.assertEqual(resultado['estado'], 'invalido')
        self.assertEqual(Asistencia.objects.count(), 0)

    def test_numero_de_otro_gimnasio_no_entra(self):
        otro_gym = Gym.objects.create(
            nombre='Otro', plan=Plan.objects.get(nombre='Basico')
        )
        ajeno = Cliente.objects.create(
            gym=otro_gym,
            sucursal=Sucursal.objects.get(gym=otro_gym),
            nombre='Ajeno',
        )

        resultado = self._ingresar(ajeno.numero_usuario)

        self.assertEqual(resultado['estado'], 'invalido')
        self.assertEqual(Asistencia.objects.count(), 0)

    def test_recargar_no_duplica_el_registro(self):
        cliente = self.crear_cliente()
        self.vender_membresia(cliente, timezone.localdate())

        self.client.post(
            reverse('clientes:checkin'), {'numero_usuario': cliente.numero_usuario}
        )
        self.client.get(reverse('clientes:checkin'))  # consume el resultado
        self.client.get(reverse('clientes:checkin'))  # recarga

        self.assertEqual(Asistencia.objects.count(), 1)

    def test_el_kiosco_solo_muestra_el_acceso(self):
        """La tablet de la entrada no expone metricas ni listados."""
        cliente = self.crear_cliente()
        self.vender_membresia(cliente, timezone.localdate())
        self.client.post(
            reverse('clientes:checkin'), {'numero_usuario': cliente.numero_usuario}
        )

        respuesta = self.client.get(reverse('clientes:checkin'))

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, 'clientes/kiosco.html')
        for sobra in ['entradas_hoy', 'vigentes', 'clientes_activos', 'ultimos', 'por_vencer']:
            self.assertNotIn(sobra, respuesta.context)

    def test_las_casillas_siguen_la_numeracion_del_gimnasio(self):
        self.crear_cliente()

        respuesta = self.client.get(reverse('clientes:checkin'))

        self.assertEqual(respuesta.context['digitos'], 4)

    def test_la_busqueda_es_una_pantalla_aparte(self):
        cliente = self.crear_cliente('Ana Torres')

        sin_buscar = self.client.get(reverse('clientes:checkin'))
        buscando = self.client.get(reverse('clientes:checkin'), {'buscar': '1', 'q': 'Ana'})

        self.assertFalse(sin_buscar.context['buscando'])
        self.assertTrue(buscando.context['buscando'])
        self.assertIn(cliente, buscando.context['coincidencias'])


class SegundoPasoEntrenamientoTest(BaseGymTest):
    """Ya adentro, la persona elige que va a entrenar."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.entrenamiento = Entrenamiento.objects.create(
            gym=cls.gym, nombre='Funcional'
        )

    def _entrar(self, cliente):
        self.client.post(
            reverse('clientes:checkin'), {'numero_usuario': cliente.numero_usuario}
        )
        return self.client.get(reverse('clientes:checkin'))

    def test_se_ofrece_a_quien_pasa(self):
        cliente = self.crear_cliente()
        self.vender_membresia(cliente, timezone.localdate())

        respuesta = self._entrar(cliente)

        self.assertIn(self.entrenamiento, respuesta.context['entrenamientos'])
        self.assertEqual(respuesta.context['segundos'], 16)

    def test_no_se_ofrece_a_quien_tiene_la_membresia_vencida(self):
        cliente = self.crear_cliente()
        self.vender_membresia(cliente, timezone.localdate() - timedelta(days=60))

        respuesta = self._entrar(cliente)

        self.assertNotIn('entrenamientos', respuesta.context)
        self.assertEqual(respuesta.context['segundos'], 7)

    def test_elegir_entrenamiento_lo_guarda_en_la_asistencia(self):
        cliente = self.crear_cliente()
        self.vender_membresia(cliente, timezone.localdate())
        respuesta = self._entrar(cliente)
        asistencia_id = respuesta.context['resultado']['asistencia_id']

        self.client.post(
            reverse('clientes:asistencia_entrenamiento', args=[asistencia_id]),
            {'entrenamiento': self.entrenamiento.pk},
        )

        asistencia = Asistencia.objects.get(pk=asistencia_id)
        self.assertEqual(asistencia.entrenamiento, self.entrenamiento)
        # No se duplica el registro: sigue siendo una sola entrada
        self.assertEqual(Asistencia.objects.count(), 1)

    def test_no_se_puede_tocar_la_asistencia_de_otro_gimnasio(self):
        otro_gym = Gym.objects.create(
            nombre='Otro', plan=Plan.objects.get(nombre='Basico')
        )
        ajena = Asistencia.objects.create(
            gym=otro_gym,
            sucursal=Sucursal.objects.get(gym=otro_gym),
            cliente=Cliente.objects.create(
                gym=otro_gym,
                sucursal=Sucursal.objects.get(gym=otro_gym),
                nombre='Ajeno',
            ),
        )

        respuesta = self.client.post(
            reverse('clientes:asistencia_entrenamiento', args=[ajena.pk]),
            {'entrenamiento': self.entrenamiento.pk},
        )

        self.assertEqual(respuesta.status_code, 404)
        ajena.refresh_from_db()
        self.assertIsNone(ajena.entrenamiento)


class SitioPublicoTest(BaseGymTest):
    def test_la_landing_es_publica(self):
        self.client.logout()
        respuesta = self.client.get(reverse('core:landing', args=[self.gym.slug]))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, self.gym.nombre)
        self.assertContains(respuesta, Gym.FRASE_DEFAULT)

    def test_usa_los_textos_y_colores_del_gimnasio(self):
        self.gym.frase_principal = 'Entrena como nunca'
        self.gym.color_primario = '#E63946'
        self.gym.save()

        respuesta = self.client.get(reverse('core:landing', args=[self.gym.slug]))

        self.assertContains(respuesta, 'Entrena como nunca')
        self.assertContains(respuesta, '#E63946')

    def test_gimnasio_sin_sitio_publico_da_404(self):
        self.gym.sitio_publico = False
        self.gym.save()

        respuesta = self.client.get(reverse('core:landing', args=[self.gym.slug]))

        self.assertEqual(respuesta.status_code, 404)

    def test_whatsapp_y_mapa_aparecen_cuando_hay_datos(self):
        self.gym.telefono = '52 55 1234 5678'
        self.gym.save()
        self.sucursal.latitud = 19.432608
        self.sucursal.longitud = -99.133209
        self.sucursal.save()

        respuesta = self.client.get(reverse('core:landing', args=[self.gym.slug]))

        self.assertContains(respuesta, 'https://wa.me/525512345678')
        self.assertContains(respuesta, 'openstreetmap.org/export/embed.html')

    def test_el_admin_edita_colores_y_frase(self):
        respuesta = self.client.post(
            reverse('core:sitio'),
            {
                'color_primario': '#00B4D8',
                'color_secundario': '#0B1A2A',
                'frase_principal': 'Tu mejor version',
                'descripcion': 'Descripcion propia.',
                'telefono': '52 55 1234 5678',
                'email': 'hola@gym.test',
                'sitio_publico': 'on',
            },
        )
        self.assertEqual(respuesta.status_code, 302)

        self.gym.refresh_from_db()
        self.assertEqual(self.gym.color_primario, '#00B4D8')
        self.assertEqual(self.gym.frase, 'Tu mejor version')

    def test_la_galeria_solo_muestra_imagenes_activas(self):
        visible = GymImagen.objects.create(
            gym=self.gym, imagen='gyms/galeria/a.jpg', titulo='Area de pesas'
        )
        oculta = GymImagen.objects.create(
            gym=self.gym, imagen='gyms/galeria/b.jpg', titulo='Vieja foto'
        )
        oculta.soft_delete()

        respuesta = self.client.get(reverse('core:landing', args=[self.gym.slug]))

        self.assertContains(respuesta, visible.titulo)
        self.assertNotContains(respuesta, oculta.titulo)
