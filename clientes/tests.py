"""Pruebas del acceso por numero de usuario y del sitio publico."""

import re
import shutil
import tempfile
from datetime import date, timedelta
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from clientes import lectores
from clientes.models import Asistencia, Cliente, ClienteMembresia, Huella, Membresia
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

    def test_el_numero_de_una_baja_no_se_reasigna(self):
        baja = self.crear_cliente('Se va')
        baja.soft_delete()
        nuevo = self.crear_cliente('Llega')
        self.assertNotEqual(nuevo.numero_usuario, baja.numero_usuario)

    def test_pasa_de_9999_a_10000(self):
        """Comparados como texto, '999' saldria mayor que '1000'."""
        tope = self.crear_cliente('Tope')
        Cliente.objects.filter(pk=tope.pk).update(numero_usuario='9999')
        self.assertEqual(self.crear_cliente('Siguiente').numero_usuario, '10000')

    def test_dos_altas_a_la_vez_no_repiten_numero(self):
        """
        Simula que otra alta se colo entre el calculo y el guardado: la primera
        vez devuelve un numero ya tomado, y el alta debe recalcular en vez de
        reventar o duplicar.
        """
        ocupado = self.crear_cliente('Primero').numero_usuario
        original = Cliente.siguiente_numero
        respuestas = [ocupado]

        def numero_pisado(gym_id):
            return respuestas.pop(0) if respuestas else original(gym_id)

        with mock.patch.object(
            Cliente, 'siguiente_numero', staticmethod(numero_pisado)
        ):
            segundo = self.crear_cliente('Segundo')

        self.assertNotEqual(segundo.numero_usuario, ocupado)
        self.assertEqual(
            Cliente.objects.filter(
                gym=self.gym, numero_usuario=segundo.numero_usuario
            ).count(),
            1,
        )

    def test_un_error_distinto_no_se_confunde_con_el_choque(self):
        """Sin sucursal el guardado falla; no debe reintentarse cinco veces."""
        with self.assertRaises(IntegrityError):
            Cliente.objects.create(gym=self.gym, sucursal=None, nombre='Sin sucursal')


class EditarNumeroDeSocioTest(BaseGymTest):
    """
    El numero se puede corregir a mano (el gimnasio llega con su propia
    numeracion, o alguien quiere el numero de su casillero), pero no deja de
    ser el identificador: dos socios con el mismo numero rompen el kiosco, que
    solo sabe de numeros.
    """

    def editar(self, cliente, numero):
        return self.client.post(
            reverse('clientes:cliente_update', args=[cliente.pk]),
            {
                'nombre': cliente.nombre,
                'sucursal': self.sucursal.pk,
                'numero_usuario': numero,
            },
        )

    def test_se_puede_cambiar_por_uno_libre(self):
        cliente = self.crear_cliente('Ana')

        self.assertEqual(self.editar(cliente, '2500').status_code, 302)

        cliente.refresh_from_db()
        self.assertEqual(cliente.numero_usuario, '2500')

    def test_uno_ocupado_se_bloquea_y_dice_de_quien_es(self):
        otro = self.crear_cliente('Ocupa')
        cliente = self.crear_cliente('Ana')
        suyo = cliente.numero_usuario

        respuesta = self.editar(cliente, otro.numero_usuario)

        # Sin redireccion: se queda en el formulario porque no guardo.
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'ya es de Ocupa')
        cliente.refresh_from_db()
        self.assertEqual(cliente.numero_usuario, suyo)

    def test_el_de_una_ficha_dada_de_baja_tampoco_se_puede_tomar(self):
        """Sus accesos y sus cobros siguen colgados de ese numero."""
        baja = self.crear_cliente('Se fue')
        baja.soft_delete()
        cliente = self.crear_cliente('Ana')

        respuesta = self.editar(cliente, baja.numero_usuario)

        self.assertContains(respuesta, 'dada de baja')
        cliente.refresh_from_db()
        self.assertNotEqual(cliente.numero_usuario, baja.numero_usuario)

    def test_el_numero_de_otro_gimnasio_no_estorba(self):
        otro_gym = Gym.objects.create(
            nombre='Otro', plan=Plan.objects.get(nombre='Basico')
        )
        ajeno = Cliente.objects.create(
            gym=otro_gym, sucursal=Sucursal.objects.get(gym=otro_gym), nombre='Ajeno'
        )
        cliente = self.crear_cliente('Ana')

        self.editar(cliente, ajeno.numero_usuario)

        cliente.refresh_from_db()
        self.assertEqual(cliente.numero_usuario, ajeno.numero_usuario)

    def test_guardar_la_ficha_sin_tocar_el_numero_no_choca_consigo_misma(self):
        cliente = self.crear_cliente('Ana')

        respuesta = self.editar(cliente, cliente.numero_usuario)

        self.assertEqual(respuesta.status_code, 302)

    def test_vaciarlo_conserva_el_que_ya_tenia(self):
        """Vaciar es 'no lo toques', no 'dame otro'."""
        cliente = self.crear_cliente('Ana')
        suyo = cliente.numero_usuario

        self.editar(cliente, '')

        cliente.refresh_from_db()
        self.assertEqual(cliente.numero_usuario, suyo)

    def test_con_letras_no_se_podria_teclear_en_el_kiosco(self):
        cliente = self.crear_cliente('Ana')

        respuesta = self.editar(cliente, 'A12')

        self.assertContains(respuesta, 'Solo digitos')
        cliente.refresh_from_db()
        self.assertNotEqual(cliente.numero_usuario, 'A12')

    def test_en_el_alta_se_sigue_asignando_solo(self):
        self.client.post(
            reverse('clientes:cliente_create'),
            {'nombre': 'Nuevo', 'sucursal': self.sucursal.pk, 'numero_usuario': ''},
        )

        self.assertEqual(Cliente.objects.get(nombre='Nuevo').numero_usuario, '1000')

    def test_en_el_alta_tambien_se_puede_elegir(self):
        self.client.post(
            reverse('clientes:cliente_create'),
            {'nombre': 'Nuevo', 'sucursal': self.sucursal.pk, 'numero_usuario': '77'},
        )

        self.assertEqual(Cliente.objects.get(nombre='Nuevo').numero_usuario, '77')

    def test_en_el_alta_uno_ocupado_tambien_se_bloquea(self):
        ocupa = self.crear_cliente('Ocupa')

        respuesta = self.client.post(
            reverse('clientes:cliente_create'),
            {
                'nombre': 'Nuevo',
                'sucursal': self.sucursal.pk,
                'numero_usuario': ocupa.numero_usuario,
            },
        )

        self.assertContains(respuesta, 'ya es de Ocupa')
        self.assertFalse(Cliente.objects.filter(nombre='Nuevo').exists())


class CredencialTest(BaseGymTest):
    def url(self, cliente):
        return reverse('clientes:cliente_credencial', args=[cliente.pk])

    def test_muestra_los_datos_del_socio(self):
        cliente = self.crear_cliente('Ana Torres')
        cuerpo = self.client.get(self.url(cliente)).content.decode()
        self.assertIn('Ana Torres', cuerpo)
        self.assertIn(cliente.numero_usuario, cuerpo)
        self.assertIn(self.gym.nombre, cuerpo)

    def test_avisa_cuando_no_hay_membresia_vigente(self):
        cliente = self.crear_cliente('Sin plan')
        self.assertIn(
            'Sin membresia vigente', self.client.get(self.url(cliente)).content.decode()
        )

    def test_no_se_ve_la_de_otro_gimnasio(self):
        otro = Gym.objects.create(nombre='Otro', plan=Plan.objects.get(nombre='Basico'))
        ajeno = Cliente.objects.create(
            gym=otro, sucursal=Sucursal.objects.get(gym=otro), nombre='Ajeno'
        )
        self.assertEqual(self.client.get(self.url(ajeno)).status_code, 404)

    def test_pide_sesion(self):
        cliente = self.crear_cliente('Con sesion')
        self.client.logout()
        self.assertEqual(self.client.get(self.url(cliente)).status_code, 302)


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

    def test_solo_salen_las_membresias_marcadas_para_el_sitio(self):
        publicada = Membresia.objects.create(
            gym=self.gym, nombre='Anual todo incluido', precio=6000,
            duracion_dias=365, visible_en_sitio=True,
        )

        respuesta = self.client.get(reverse('core:landing', args=[self.gym.slug]))

        self.assertContains(respuesta, publicada.nombre)
        # La del catalogo interno nace oculta y no debe asomarse
        self.assertNotContains(respuesta, self.membresia.nombre)

    def test_el_admin_elige_que_membresias_se_publican(self):
        otra = Membresia.objects.create(
            gym=self.gym, nombre='Semanal', precio=200, duracion_dias=7,
            visible_en_sitio=True,
        )

        respuesta = self.client.post(
            reverse('core:sitio_membresias'), {'visibles': [str(self.membresia.pk)]}
        )
        self.assertEqual(respuesta.status_code, 302)

        self.membresia.refresh_from_db()
        otra.refresh_from_db()
        self.assertTrue(self.membresia.visible_en_sitio)
        # Desmarcar es no mandarla: la que se quedo fuera se despublica
        self.assertFalse(otra.visible_en_sitio)

    def test_no_se_publican_membresias_de_otro_gimnasio(self):
        otro_gym = Gym.objects.create(
            nombre='Ajeno', plan=Plan.objects.get(nombre='Basico')
        )
        ajena = Membresia.objects.create(
            gym=otro_gym, nombre='Ajena', precio=100, duracion_dias=30
        )

        self.client.post(reverse('core:sitio_membresias'), {'visibles': [str(ajena.pk)]})

        ajena.refresh_from_db()
        self.assertFalse(ajena.visible_en_sitio)

    def test_la_foto_de_la_membresia_sale_en_la_tarjeta(self):
        Membresia.objects.create(
            gym=self.gym, nombre='Anual', precio=6000, duracion_dias=365,
            visible_en_sitio=True, foto='membresias/anual.jpg',
        )

        respuesta = self.client.get(reverse('core:landing', args=[self.gym.slug]))

        self.assertContains(respuesta, 'membresias/anual.jpg')


# Sin esto los archivos de prueba se quedan en la carpeta media del proyecto.
@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class FotoDeMembresiaTest(BaseGymTest):
    """La foto es lo que vende el plan en la pagina publica."""

    #: GIF de un pixel: ImageField pide que Pillow pueda abrir el archivo.
    PIXEL = (
        b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!'
        b'\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00'
        b'\x00\x02\x02D\x01\x00;'
    )

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def editar(self, **extra):
        datos = {
            'nombre': 'Mensual',
            'precio': '600',
            'duracion_dias': '30',
            'descripcion': '',
        }
        datos.update(extra)
        return self.client.post(
            reverse('clientes:membresia_update', args=[self.membresia.pk]), datos
        )

    def test_se_sube_al_editar_la_membresia(self):
        respuesta = self.editar(
            foto=SimpleUploadedFile('plan.gif', self.PIXEL, content_type='image/gif')
        )
        self.assertEqual(respuesta.status_code, 302)

        self.membresia.refresh_from_db()
        self.assertIn('membresias/', self.membresia.foto.name)

    def test_sigue_siendo_opcional(self):
        self.assertEqual(self.editar().status_code, 302)

        self.membresia.refresh_from_db()
        self.assertFalse(self.membresia.foto)


class RenovacionTest(BaseGymTest):
    """Renovar antes de tiempo no debe borrar los dias ya pagados."""

    def url(self):
        return reverse('clientes:clientemembresia_create')

    def vender(self, cliente, inicio=None):
        return self.client.post(self.url(), {
            'cliente': str(cliente.pk),
            'membresia': self.membresia.pk,
            'inicio': (inicio or timezone.localdate()).isoformat(),
            'precio': '600', 'descuento': '0', 'metodo_pago': 'efectivo',
        })

    def test_sin_membresia_previa_arranca_hoy(self):
        cliente = self.crear_cliente('Nuevo')
        self.vender(cliente)
        self.assertEqual(
            ClienteMembresia.objects.get(cliente=cliente).inicio, timezone.localdate()
        )

    def test_renovar_antes_de_vencer_encadena(self):
        cliente = self.crear_cliente('Renueva')
        hoy = timezone.localdate()
        vieja = self.vender_membresia(cliente, hoy - timedelta(days=20))

        self.vender(cliente)

        nueva = ClienteMembresia.objects.filter(cliente=cliente).exclude(
            pk=vieja.pk
        ).get()
        self.assertEqual(nueva.inicio, vieja.fin + timedelta(days=1))
        self.assertEqual(
            nueva.fin, nueva.inicio + timedelta(days=self.membresia.duracion_dias)
        )

    def test_renovar_ya_vencida_arranca_hoy(self):
        cliente = self.crear_cliente('Vencida')
        self.vender_membresia(cliente, timezone.localdate() - timedelta(days=90))

        self.vender(cliente)

        nueva = ClienteMembresia.objects.filter(cliente=cliente).order_by('-pk').first()
        self.assertEqual(nueva.inicio, timezone.localdate())

    def test_la_fecha_que_propone_la_pantalla_no_pierde_dias(self):
        cliente = self.crear_cliente('Propuesta')
        vigente = self.vender_membresia(
            cliente, timezone.localdate() - timedelta(days=20)
        )
        respuesta = self.client.get(f'{self.url()}?cliente={cliente.pk}')
        self.assertEqual(
            respuesta.context['form'].initial['inicio'], vigente.fin + timedelta(days=1)
        )

    def test_una_cancelada_no_estorba_la_siguiente(self):
        cliente = self.crear_cliente('Cancelo')
        vieja = self.vender_membresia(cliente, timezone.localdate() - timedelta(days=5))
        ClienteMembresia.objects.filter(pk=vieja.pk).update(estado='cancelada')

        self.vender(cliente)

        nueva = ClienteMembresia.objects.filter(cliente=cliente).exclude(
            pk=vieja.pk
        ).get()
        self.assertEqual(nueva.inicio, timezone.localdate())


class EditarCancelarMembresiaTest(BaseGymTest):
    def setUp(self):
        super().setUp()
        self.cliente = self.crear_cliente('Socio')
        self.venta = self.vender_membresia(self.cliente, timezone.localdate())

    def test_editar_corrige_el_precio(self):
        respuesta = self.client.post(
            reverse('clientes:clientemembresia_update', args=[self.venta.pk]),
            {
                'cliente': str(self.cliente.pk), 'membresia': self.membresia.pk,
                'inicio': self.venta.inicio.isoformat(),
                'precio': '450', 'descuento': '0', 'metodo_pago': 'tarjeta',
            },
        )
        self.assertEqual(respuesta.status_code, 302)
        self.venta.refresh_from_db()
        self.assertEqual(self.venta.precio, 450)
        self.assertEqual(self.venta.metodo_pago, 'tarjeta')

    def test_editar_no_se_encadena_consigo_misma(self):
        inicio = self.venta.inicio
        self.client.post(
            reverse('clientes:clientemembresia_update', args=[self.venta.pk]),
            {
                'cliente': str(self.cliente.pk), 'membresia': self.membresia.pk,
                'inicio': inicio.isoformat(), 'precio': '600',
                'descuento': '0', 'metodo_pago': 'efectivo',
            },
        )
        self.venta.refresh_from_db()
        self.assertEqual(self.venta.inicio, inicio)

    def test_cancelar_no_borra_el_registro(self):
        self.client.post(
            reverse('clientes:clientemembresia_cancelar', args=[self.venta.pk])
        )
        self.venta.refresh_from_db()
        self.assertEqual(self.venta.estado, 'cancelada')
        self.assertTrue(ClienteMembresia.objects.filter(pk=self.venta.pk).exists())

    def test_una_cancelada_ya_no_se_edita(self):
        ClienteMembresia.objects.filter(pk=self.venta.pk).update(estado='cancelada')
        respuesta = self.client.get(
            reverse('clientes:clientemembresia_update', args=[self.venta.pk])
        )
        self.assertEqual(respuesta.status_code, 404)

    def test_no_se_edita_la_de_otro_gimnasio(self):
        otro = Gym.objects.create(nombre='Otro', plan=Plan.objects.get(nombre='Basico'))
        ajeno = Cliente.objects.create(
            gym=otro, sucursal=Sucursal.objects.get(gym=otro), nombre='Ajeno'
        )
        suya = ClienteMembresia.objects.create(
            gym=otro, cliente=ajeno,
            membresia=Membresia.objects.create(
                gym=otro, nombre='X', precio=100, duracion_dias=30
            ),
            precio=100,
        )
        respuesta = self.client.post(
            reverse('clientes:clientemembresia_cancelar', args=[suya.pk])
        )
        self.assertEqual(respuesta.status_code, 404)

    def test_cancelar_no_redirige_fuera_del_sitio(self):
        """El destino viaja en el POST: hay que comprobarlo antes de usarlo."""
        respuesta = self.client.post(
            reverse('clientes:clientemembresia_cancelar', args=[self.venta.pk]),
            {'volver': 'https://ejemplo-malicioso.test/'},
        )
        self.assertNotIn('ejemplo-malicioso', respuesta['Location'])


class CamposDeFechaTest(BaseGymTest):
    """
    <input type="date"> solo entiende aaaa-mm-dd. Con el idioma en espanol
    Django rendiriza 14/05/1990, el navegador lo descarta sin avisar y el campo
    sale vacio: al guardar se pierde el dato.
    """

    def campo(self, html, nombre):
        return re.search(rf'<input[^>]*name="{nombre}"[^>]*>', html).group(0)

    def test_el_nacimiento_llega_al_navegador(self):
        cliente = self.crear_cliente('Con fecha')
        Cliente.objects.filter(pk=cliente.pk).update(fecha_nacimiento=date(1990, 5, 14))

        html = self.client.get(
            reverse('clientes:cliente_update', args=[cliente.pk])
        ).content.decode()

        self.assertIn('value="1990-05-14"', self.campo(html, 'fecha_nacimiento'))

    def test_editar_no_borra_el_nacimiento(self):
        cliente = self.crear_cliente('No se borra')
        Cliente.objects.filter(pk=cliente.pk).update(fecha_nacimiento=date(1990, 5, 14))

        html = self.client.get(
            reverse('clientes:cliente_update', args=[cliente.pk])
        ).content.decode()
        valor = re.search(r'value="([\d-]+)"', self.campo(html, 'fecha_nacimiento'))
        # Se reenvia tal cual lo mandaria el navegador con ese valor.
        self.client.post(
            reverse('clientes:cliente_update', args=[cliente.pk]),
            {
                'nombre': cliente.nombre, 'sucursal': self.sucursal.pk,
                'fecha_nacimiento': valor.group(1),
            },
        )

        cliente.refresh_from_db()
        self.assertEqual(cliente.fecha_nacimiento, date(1990, 5, 14))

    def test_el_inicio_propuesto_llega_al_navegador(self):
        cliente = self.crear_cliente('Renueva')
        vigente = self.vender_membresia(
            cliente, timezone.localdate() - timedelta(days=10)
        )

        html = self.client.get(
            f'{reverse("clientes:clientemembresia_create")}?cliente={cliente.pk}'
        ).content.decode()

        esperado = (vigente.fin + timedelta(days=1)).isoformat()
        self.assertIn(f'value="{esperado}"', self.campo(html, 'inicio'))


class PrecioYDescuentoOpcionalesTest(BaseGymTest):
    def setUp(self):
        super().setUp()
        self.cliente = self.crear_cliente('Socio')

    def vender(self, **extra):
        return self.client.post(reverse('clientes:clientemembresia_create'), {
            'cliente': str(self.cliente.pk),
            'membresia': self.membresia.pk,
            'inicio': timezone.localdate().isoformat(),
            'metodo_pago': 'efectivo',
            **extra,
        })

    def test_salen_vacios_y_no_con_un_cero_puesto(self):
        html = self.client.get(
            reverse('clientes:clientemembresia_create')
        ).content.decode()
        for nombre in ('precio', 'descuento'):
            campo = re.search(rf'<input[^>]*name="{nombre}"[^>]*>', html).group(0)
            self.assertNotIn('value=', campo)
            self.assertIn('placeholder="0"', campo)

    def test_sin_precio_toma_el_de_la_membresia(self):
        self.vender()
        venta = ClienteMembresia.objects.get(cliente=self.cliente)
        self.assertEqual(venta.precio, self.membresia.precio)
        self.assertEqual(venta.descuento, 0)

    def test_un_precio_distinto_manda_sobre_el_del_catalogo(self):
        self.vender(precio='450')
        self.assertEqual(
            ClienteMembresia.objects.get(cliente=self.cliente).precio, 450
        )

    def test_un_precio_de_cero_se_respeta(self):
        """Una cortesia vale 0, y eso no es lo mismo que dejarlo en blanco."""
        self.vender(precio='0')
        self.assertEqual(ClienteMembresia.objects.get(cliente=self.cliente).precio, 0)


class CancelarQuitaElAccesoTest(BaseGymTest):
    """
    Cancelar dejaba las fechas intactas, asi que la membresia seguia
    abarcando hoy y el socio entraba con algo ya deshecho.
    """

    def setUp(self):
        super().setUp()
        self.cliente = self.crear_cliente('Socio')
        self.venta = self.vender_membresia(self.cliente, timezone.localdate())

    def cancelar(self):
        return self.client.post(
            reverse('clientes:clientemembresia_cancelar', args=[self.venta.pk])
        )

    def test_deja_de_estar_vigente(self):
        self.assertTrue(self.cliente.esta_al_corriente)

        self.cancelar()

        self.assertFalse(self.cliente.esta_al_corriente)
        self.assertIsNone(self.cliente.membresia_vigente)

    def test_ya_no_puede_entrar(self):
        self.cancelar()

        self.client.post(
            reverse('clientes:checkin'),
            {'numero_usuario': self.cliente.numero_usuario},
        )

        self.assertNotEqual(self.client.session['acceso']['estado'], 'ok')

    def test_no_aparece_como_su_ultima_membresia(self):
        """El aviso del acceso hablaria de algo que se deshizo."""
        self.cancelar()
        self.assertIsNone(self.cliente.ultima_membresia)

    def test_deja_de_contar_en_la_caja(self):
        hoy = timezone.localdate()
        self.assertEqual(
            sum(cm.total for cm in ClienteMembresia.cobradas_aparte(self.gym, hoy)),
            600,
        )

        self.cancelar()

        self.assertEqual(
            sum(cm.total for cm in ClienteMembresia.cobradas_aparte(self.gym, hoy)), 0
        )

    def test_el_tablero_deja_de_contarla_en_la_cartera(self):
        self.cancelar()

        respuesta = self.client.get(reverse('core:dashboard'))

        self.assertEqual(respuesta.context['membresias_vigentes'], 0)
        self.assertEqual(respuesta.context['sin_membresia'], 1)

    def test_libera_la_fecha_para_la_siguiente(self):
        """Encadenar tras una cancelada regalaria dias que ya nadie pago."""
        self.cancelar()
        self.assertEqual(
            self.cliente.inicio_siguiente_membresia, timezone.localdate()
        )


class FiltrosDeClientesTest(BaseGymTest):
    """Los mismos cortes del tablero, para ver quien hay detras del numero."""

    def setUp(self):
        super().setUp()
        hoy = timezone.localdate()
        self.al_corriente = self.crear_cliente('Al corriente')
        self.vender_membresia(self.al_corriente, hoy)

        self.por_vencer = self.crear_cliente('Por vencer')
        self.vender_membresia(self.por_vencer, hoy - timedelta(days=27))

        self.sin_nada = self.crear_cliente('Sin nada')

        self.vencido = self.crear_cliente('Vencido')
        self.vender_membresia(self.vencido, hoy - timedelta(days=90))

    def filtrar(self, estado):
        respuesta = self.client.get(
            reverse('clientes:cliente_list'), {'estado': estado}
        )
        return [c.nombre for c in respuesta.context['clientes']]

    def test_sin_membresia_junta_a_quien_hoy_no_puede_entrar(self):
        nombres = self.filtrar('sin_membresia')
        self.assertCountEqual(nombres, ['Sin nada', 'Vencido'])

    def test_por_vencer_son_los_de_los_dias_de_aviso(self):
        self.assertEqual(self.filtrar('por_vencer'), ['Por vencer'])

    def test_vencida_deja_fuera_a_quien_nunca_compro(self):
        """
        Es el corte al que manda el tablero. 'Sin membresia' tambien sirve,
        pero mete a quien nunca compro, y a ese no se le habla para renovar.
        """
        self.assertEqual(self.filtrar('vencida'), ['Vencido'])

    def test_al_corriente_excluye_a_los_que_ya_urgen(self):
        self.assertEqual(self.filtrar('al_corriente'), ['Al corriente'])

    def test_una_cancelada_cae_en_sin_membresia(self):
        venta = self.al_corriente.membresias.get()
        ClienteMembresia.objects.filter(pk=venta.pk).update(estado='cancelada')

        self.assertIn('Al corriente', self.filtrar('sin_membresia'))

    def test_sin_filtro_salen_todos(self):
        respuesta = self.client.get(reverse('clientes:cliente_list'))
        self.assertEqual(len(respuesta.context['clientes']), 4)

    def test_un_filtro_inventado_no_recorta_la_lista(self):
        self.assertEqual(len(self.filtrar('lo-que-sea')), 4)


class LlegarALaFichaTest(BaseGymTest):
    """
    El nombre en azul era la unica puerta al perfil, y nada lo anunciaba.
    """

    def setUp(self):
        super().setUp()
        self.cliente = self.crear_cliente('Ana Torres')
        self.lista = self.client.get(reverse('clientes:cliente_list')).content.decode()
        self.ficha_url = reverse('clientes:cliente_detail', args=[self.cliente.pk])

    def test_la_lista_dice_que_hay_una_ficha(self):
        self.assertIn('Ficha', self.lista)
        self.assertIn(self.ficha_url, self.lista)

    def test_la_fila_no_se_llena_de_acciones(self):
        """Editar y dar de baja se hacen dentro, donde se ve a quien le pegan."""
        self.assertNotIn(
            reverse('clientes:cliente_update', args=[self.cliente.pk]), self.lista
        )
        self.assertNotIn(
            reverse('clientes:cliente_delete', args=[self.cliente.pk]), self.lista
        )

    def test_vender_sigue_a_la_mano_desde_la_fila(self):
        self.assertIn(
            f"{reverse('clientes:clientemembresia_create')}?cliente={self.cliente.pk}",
            self.lista,
        )


class AccionesDeLaFichaTest(BaseGymTest):
    """Cinco botones en fila no dejaban ver cual importa."""

    def setUp(self):
        super().setUp()
        self.cliente = self.crear_cliente('Ana Torres')
        self.ficha = self.client.get(
            reverse('clientes:cliente_detail', args=[self.cliente.pk])
        ).content.decode()

    def test_solo_una_accion_principal(self):
        self.assertEqual(self.ficha.count('btn-primario'), 1)

    def test_y_es_la_que_deja_dinero(self):
        self.assertIn('Vender membresia', self.ficha)

    def test_dice_renovar_cuando_ya_tiene(self):
        self.vender_membresia(self.cliente, timezone.localdate())

        ficha = self.client.get(
            reverse('clientes:cliente_detail', args=[self.cliente.pk])
        ).content.decode()

        self.assertIn('Renovar membresia', ficha)

    def test_lo_demas_sigue_estando(self):
        for url in (
            reverse('clientes:cliente_update', args=[self.cliente.pk]),
            reverse('clientes:cliente_credencial', args=[self.cliente.pk]),
            reverse('clientes:cliente_delete', args=[self.cliente.pk]),
            reverse('clientes:asistencia_registrar', args=[self.cliente.pk]),
            reverse('bot:codigo_vinculacion', args=[self.cliente.pk]),
        ):
            with self.subTest(url=url):
                self.assertIn(url, self.ficha)

    def test_dar_de_baja_desde_la_ficha_funciona(self):
        """Se movio de la lista al menu: la baja tiene que seguir corriendo."""
        self.client.post(reverse('clientes:cliente_delete', args=[self.cliente.pk]))

        self.cliente.refresh_from_db()
        self.assertFalse(self.cliente.activo)


# Sin esto los archivos de prueba se quedan en la carpeta media del proyecto.
@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ComprobanteDePagoTest(BaseGymTest):
    """
    Foto del ticket o PDF de la transferencia, para aclarar un cobro que el
    socio reclama meses despues.
    """

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.cliente = self.crear_cliente('Ana Torres')

    @staticmethod
    def archivo(nombre='ticket.jpg', peso=1024, tipo='image/jpeg'):
        return SimpleUploadedFile(nombre, b'x' * peso, content_type=tipo)

    def vender(self, comprobante=None):
        datos = {
            'cliente': str(self.cliente.pk),
            'membresia': str(self.membresia.pk),
            'inicio': timezone.localdate().isoformat(),
            'metodo_pago': 'transferencia',
            'precio': '600',
            'descuento': '',
            'observaciones': '',
        }
        if comprobante is not None:
            datos['comprobante'] = comprobante
        return self.client.post(reverse('clientes:clientemembresia_create'), datos)

    def test_se_guarda_junto_a_la_venta(self):
        self.vender(self.archivo())

        venta = ClienteMembresia.objects.get()
        self.assertTrue(venta.comprobante)
        self.assertEqual(venta.comprobante.read(), b'x' * 1024)

    def test_el_nombre_original_no_se_conserva(self):
        """Viven en un bucket publico: 'ticket.jpg' seria una url adivinable."""
        self.vender(self.archivo('ticket.jpg'))

        ruta = ClienteMembresia.objects.get().comprobante.name

        self.assertNotIn('ticket', ruta)
        self.assertTrue(ruta.endswith('.jpg'))

    def test_queda_separado_por_gimnasio(self):
        self.vender(self.archivo())

        self.assertIn(
            f'comprobantes/{self.gym.pk}/', ClienteMembresia.objects.get().comprobante.name
        )

    def test_sigue_siendo_opcional(self):
        self.vender()

        venta = ClienteMembresia.objects.get()
        self.assertFalse(venta.comprobante)

    def test_un_pdf_tambien_entra(self):
        self.vender(self.archivo('banco.pdf', tipo='application/pdf'))

        self.assertTrue(ClienteMembresia.objects.get().comprobante)

    def test_un_ejecutable_no(self):
        respuesta = self.vender(self.archivo('virus.exe', tipo='application/exe'))

        self.assertEqual(ClienteMembresia.objects.count(), 0)
        self.assertContains(respuesta, 'extensi', status_code=200)

    def test_uno_enorme_tampoco(self):
        gordo = self.archivo(peso=11 * 1024 * 1024)

        respuesta = self.vender(gordo)

        self.assertEqual(ClienteMembresia.objects.count(), 0)
        self.assertContains(respuesta, '10 MB', status_code=200)

    def test_el_formulario_acepta_archivos(self):
        """Sin enctype el navegador manda el nombre y no el archivo."""
        respuesta = self.client.get(reverse('clientes:clientemembresia_create'))

        self.assertContains(respuesta, 'enctype="multipart/form-data"')
        self.assertContains(respuesta, 'type="file"')

    def test_se_puede_abrir_desde_la_ficha(self):
        self.vender(self.archivo())
        venta = ClienteMembresia.objects.get()

        respuesta = self.client.get(
            reverse('clientes:cliente_detail', args=[self.cliente.pk])
        )

        self.assertContains(respuesta, venta.comprobante.url)

    def test_editar_sin_tocarlo_no_lo_borra(self):
        self.vender(self.archivo())
        venta = ClienteMembresia.objects.get()
        antes = venta.comprobante.name

        self.client.post(reverse('clientes:clientemembresia_update', args=[venta.pk]), {
            'cliente': str(self.cliente.pk),
            'membresia': str(self.membresia.pk),
            'inicio': venta.inicio.isoformat(),
            'metodo_pago': 'efectivo',
            'precio': '700',
            'descuento': '',
            'observaciones': '',
        })

        venta.refresh_from_db()
        self.assertEqual(venta.comprobante.name, antes)
        self.assertEqual(venta.precio, 700)


class AccesoPorHuellaTest(BaseGymTest):
    """
    El acceso por huella tiene que dar exactamente el mismo veredicto que el
    numero tecleado, y el numero tiene que seguir sirviendo siempre: el lector
    se va a desconectar y el gimnasio no se puede parar por eso.
    """

    def setUp(self):
        super().setUp()
        self.ana = self.crear_cliente('Ana Torres')
        self.beto = self.crear_cliente('Beto Ruiz')
        lectores.retirar()

    def tearDown(self):
        lectores.retirar()
        super().tearDown()

    def enrolar(self, cliente, dedo_simulado, dedo='indice_der'):
        lectores.presentar(dedo_simulado)
        return self.client.post(
            reverse('clientes:huella_enrolar', args=[cliente.pk]), {'dedo': dedo}
        )

    def entrar_con_huella(self, dedo_simulado):
        lectores.presentar(dedo_simulado)
        self.client.post(reverse('clientes:checkin_huella'))
        return self.client.get(reverse('clientes:checkin')).context['resultado']

    # --- Enrolamiento -----------------------------------------------------

    def test_se_enrola_desde_la_ficha_del_socio(self):
        self.enrolar(self.ana, 'dedo-de-ana')

        huella = Huella.objects.get(cliente=self.ana)
        self.assertEqual(huella.dedo, 'indice_der')
        self.assertEqual(huella.gym, self.gym)
        self.assertTrue(bytes(huella.plantilla))

    def test_no_se_guarda_una_lectura_de_mala_calidad(self):
        lectores.presentar('dedo-de-ana', calidad=20)
        self.client.post(
            reverse('clientes:huella_enrolar', args=[self.ana.pk]),
            {'dedo': 'indice_der'},
        )

        self.assertFalse(Huella.objects.exists())

    def test_no_se_enrola_el_mismo_dedo_a_dos_socios(self):
        self.enrolar(self.ana, 'dedo-de-ana')

        self.enrolar(self.beto, 'dedo-de-ana')

        # Si se dejara pasar, el acceso dejaria entrar al que la comparacion
        # encuentre primero y el otro quedaria fuera sin explicacion.
        self.assertEqual(Huella.objects.count(), 1)
        self.assertEqual(Huella.objects.get().cliente, self.ana)

    def test_reenrolar_el_mismo_dedo_reemplaza_la_plantilla(self):
        self.enrolar(self.ana, 'dedo-de-ana')
        antes = bytes(Huella.objects.get().plantilla)

        self.enrolar(self.ana, 'dedo-de-ana')

        self.assertEqual(Huella.objects.count(), 1)
        self.assertNotEqual(bytes(Huella.objects.get().plantilla), antes)

    def test_se_puede_quitar_y_volver_a_enrolar(self):
        self.enrolar(self.ana, 'dedo-de-ana')

        self.client.post(
            reverse('clientes:huella_borrar', args=[Huella.objects.get().pk])
        )
        self.assertFalse(Huella.objects.exists())

        self.enrolar(self.ana, 'dedo-de-ana')
        self.assertEqual(Huella.objects.count(), 1)

    # --- Acceso -----------------------------------------------------------

    def test_la_huella_registra_la_entrada_igual_que_el_numero(self):
        self.enrolar(self.ana, 'dedo-de-ana')
        self.vender_membresia(self.ana, timezone.localdate())

        resultado = self.entrar_con_huella('dedo-de-ana')

        self.assertEqual(resultado['estado'], 'ok')
        self.assertEqual(resultado['nombre'], 'Ana Torres')
        self.assertEqual(Asistencia.objects.get().cliente, self.ana)

    def test_distingue_entre_dos_socios_enrolados(self):
        self.enrolar(self.ana, 'dedo-de-ana')
        self.enrolar(self.beto, 'dedo-de-beto')

        resultado = self.entrar_con_huella('dedo-de-beto')

        self.assertEqual(resultado['nombre'], 'Beto Ruiz')

    def test_la_membresia_vencida_se_avisa_igual_que_con_el_numero(self):
        self.enrolar(self.ana, 'dedo-de-ana')

        resultado = self.entrar_con_huella('dedo-de-ana')

        self.assertEqual(resultado['estado'], 'vencida')

    def test_un_dedo_desconocido_no_deja_pasar(self):
        self.enrolar(self.ana, 'dedo-de-ana')

        resultado = self.entrar_con_huella('dedo-de-un-desconocido')

        self.assertEqual(resultado['estado'], 'invalido')
        self.assertFalse(Asistencia.objects.exists())

    def test_sin_lector_conectado_lo_dice_y_no_truena(self):
        self.enrolar(self.ana, 'dedo-de-ana')
        lectores.retirar()

        self.client.post(reverse('clientes:checkin_huella'))
        resultado = self.client.get(reverse('clientes:checkin')).context['resultado']

        self.assertEqual(resultado['estado'], 'invalido')
        self.assertFalse(Asistencia.objects.exists())

    def test_el_numero_sigue_funcionando_con_huellas_enroladas(self):
        self.enrolar(self.ana, 'dedo-de-ana')
        self.ana.refresh_from_db()

        self.client.post(
            reverse('clientes:checkin'), {'numero_usuario': self.ana.numero_usuario}
        )
        resultado = self.client.get(reverse('clientes:checkin')).context['resultado']

        self.assertEqual(resultado['nombre'], 'Ana Torres')

    def test_no_se_reconoce_la_huella_de_otro_gimnasio(self):
        otro_gym = Gym.objects.create(
            nombre='Ajeno', plan=Plan.objects.get(nombre='Basico')
        )
        ajeno = Cliente.objects.create(
            gym=otro_gym,
            sucursal=Sucursal.objects.get(gym=otro_gym),
            nombre='Socio Ajeno',
        )
        lector = lectores.LectorFalso()
        Huella.objects.create(
            gym=otro_gym, cliente=ajeno, dedo='indice_der',
            plantilla=lector.plantilla_de('dedo-ajeno'), calidad=90,
        )

        resultado = self.entrar_con_huella('dedo-ajeno')

        self.assertEqual(resultado['estado'], 'invalido')
        self.assertFalse(Asistencia.objects.exists())

    def test_el_boton_de_huella_solo_sale_si_hay_alguna_enrolada(self):
        sin = self.client.get(reverse('clientes:checkin'))
        self.assertNotContains(sin, 'checkin_huella')
        self.assertFalse(sin.context['hay_huellas'])

        self.enrolar(self.ana, 'dedo-de-ana')

        con = self.client.get(reverse('clientes:checkin'))
        self.assertTrue(con.context['hay_huellas'])


class LectorFalsoTest(TestCase):
    """
    El lector de mentiras tiene que portarse como uno de verdad, o las pruebas
    de arriba no prueban nada.
    """

    def test_dos_lecturas_del_mismo_dedo_no_son_identicas_pero_se_parecen(self):
        lector = lectores.LectorFalso(dedo='mismo')

        a, b = lector.capturar().plantilla, lector.capturar().plantilla

        self.assertNotEqual(a, b)
        self.assertGreaterEqual(lector.comparar(a, b), lectores.UMBRAL)

    def test_dos_dedos_distintos_no_se_parecen(self):
        uno = lectores.LectorFalso(dedo='uno').capturar().plantilla
        otro = lectores.LectorFalso(dedo='otro').capturar().plantilla

        self.assertLess(lectores.LectorFalso().comparar(uno, otro), lectores.UMBRAL)

    def test_identificar_devuelve_el_que_mas_se_parece_no_el_primero(self):
        lector = lectores.LectorFalso()
        candidatas = [
            (1, lector.plantilla_de('otro')),
            (2, lector.plantilla_de('buscado')),
        ]

        quien, puntaje = lector.identificar(lector.plantilla_de('buscado'), candidatas)

        self.assertEqual(quien, 2)
        self.assertEqual(puntaje, 100)

    def test_sin_dedo_en_el_sensor_avisa(self):
        with self.assertRaises(lectores.ErrorDeLector):
            lectores.LectorFalso().capturar()
