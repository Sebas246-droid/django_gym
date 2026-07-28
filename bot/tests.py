"""Pruebas del bot de Telegram: vinculacion, consultas y calculadora."""

import json
from datetime import date, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bot import conversacion
from bot.conversacion import responder
from bot.models import BotTelegram, ClienteTelegram, CodigoVinculacion, MedidaCorporal
from clientes.models import Cliente, ClienteMembresia, Membresia
from core.models import Gym, Plan, Sucursal

User = get_user_model()

CHAT = 987654


class BaseBotTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('init_saas')
        cls.gym = Gym.objects.create(
            nombre='Iron House', plan=Plan.objects.get(nombre='Pro')
        )
        cls.sucursal = Sucursal.objects.get(gym=cls.gym, nombre='Principal')
        cls.bot = BotTelegram.objects.create(gym=cls.gym, token='123:ABC')
        # El 1 de enero de hace 30 anos da exactamente 30 cualquier dia del ano;
        # restar 365*30 dias no, por los bisiestos.
        cls.cliente = Cliente.objects.create(
            gym=cls.gym, sucursal=cls.sucursal, nombre='Ana Torres',
            sexo='F', fecha_nacimiento=date(timezone.localdate().year - 30, 1, 1),
        )

    def vincular(self, cliente=None):
        return ClienteTelegram.objects.create(
            cliente=cliente or self.cliente, chat_id=CHAT
        )


class VinculacionTest(BaseBotTest):
    def test_sin_vincular_pide_el_codigo(self):
        r = responder(self.gym, CHAT, '/start')
        self.assertIn('codigo de acceso', r.texto)

    def test_el_codigo_correcto_vincula(self):
        codigo = CodigoVinculacion.emitir(self.cliente)
        r = responder(self.gym, CHAT, codigo.codigo)
        self.assertIn('Ana Torres', r.texto)
        self.assertTrue(
            ClienteTelegram.objects.filter(cliente=self.cliente, chat_id=CHAT).exists()
        )

    def test_el_codigo_se_gasta_una_sola_vez(self):
        codigo = CodigoVinculacion.emitir(self.cliente)
        responder(self.gym, CHAT, codigo.codigo)
        ClienteTelegram.objects.all().delete()
        r = responder(self.gym, 111, codigo.codigo)
        self.assertIn('no sirve', r.texto)

    def test_el_codigo_vencido_no_sirve(self):
        codigo = CodigoVinculacion.emitir(self.cliente)
        CodigoVinculacion.objects.filter(pk=codigo.pk).update(
            expira_en=timezone.now() - timedelta(minutes=1)
        )
        r = responder(self.gym, CHAT, codigo.codigo)
        self.assertIn('no sirve', r.texto)

    def test_el_codigo_de_otro_gimnasio_no_sirve(self):
        otro = Gym.objects.create(nombre='Otro', plan=Plan.objects.get(nombre='Basico'))
        ajeno = Cliente.objects.create(
            gym=otro, sucursal=Sucursal.objects.get(gym=otro), nombre='Ajeno'
        )
        codigo = CodigoVinculacion.emitir(ajeno)
        r = responder(self.gym, CHAT, codigo.codigo)
        self.assertIn('no sirve', r.texto)

    def test_pedir_codigo_nuevo_invalida_el_anterior(self):
        viejo = CodigoVinculacion.emitir(self.cliente)
        CodigoVinculacion.emitir(self.cliente)
        self.assertFalse(CodigoVinculacion.objects.filter(pk=viejo.pk).exists())

    def test_salir_desvincula(self):
        self.vincular()
        r = responder(self.gym, CHAT, '/salir')
        self.assertIn('Desvinculado', r.texto)
        self.assertIn('codigo de acceso', responder(self.gym, CHAT, 'Hola').texto)


class ConsultasTest(BaseBotTest):
    def setUp(self):
        self.enlace = self.vincular()

    def test_membresia_vigente(self):
        membresia = Membresia.objects.create(
            gym=self.gym, nombre='Mensual', precio=600, duracion_dias=30
        )
        ClienteMembresia.objects.create(
            gym=self.gym, cliente=self.cliente, membresia=membresia,
            inicio=timezone.localdate(), precio=600,
        )
        r = responder(self.gym, CHAT, conversacion.MEMBRESIA)
        self.assertIn('vigente hasta', r.texto)

    def test_sin_membresia(self):
        r = responder(self.gym, CHAT, conversacion.MEMBRESIA)
        self.assertIn('No tienes ninguna membresia', r.texto)

    def test_sin_asistencias(self):
        r = responder(self.gym, CHAT, conversacion.ASISTENCIAS)
        self.assertIn('Todavia no tienes visitas', r.texto)

    def test_opcion_desconocida_devuelve_al_menu(self):
        r = responder(self.gym, CHAT, 'cualquier cosa')
        self.assertIn('los botones', r.texto)
        self.assertEqual(r.botones, conversacion.MENU)


class CalculadoraTest(BaseBotTest):
    def setUp(self):
        self.enlace = self.vincular()

    def _paso(self, texto):
        return responder(self.gym, CHAT, texto)

    def test_flujo_de_tres_preguntas(self):
        """Con sexo y fecha de nacimiento en la ficha solo faltan tres datos."""
        self.assertIn('kilos', self._paso(conversacion.CALORIAS).texto)
        self.assertIn('centimetros', self._paso('70').texto)
        self.assertIn('dias por semana', self._paso('165').texto)
        final = self._paso('3 a 5 dias por semana')

        self.assertIn('mantenerte', final.texto)
        self.assertIn('bajar', final.texto)
        self.assertIn('no una indicacion nutricional', final.texto.lower())

    def test_guarda_el_peso_como_historico(self):
        self._paso(conversacion.CALORIAS)
        self._paso('70')
        self._paso('165')
        self._paso('3 a 5 dias por semana')
        medida = MedidaCorporal.objects.get(cliente=self.cliente)
        self.assertEqual(float(medida.peso_kg), 70.0)

    def test_lo_contestado_se_queda_en_la_ficha(self):
        """La estatura y la actividad no cambian: no hay que volver a pedirlas."""
        self._paso(conversacion.CALORIAS)
        self._paso('70')
        self._paso('165')
        self._paso('3 a 5 dias por semana')

        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.estatura_cm, 165)
        self.assertEqual(self.cliente.nivel_actividad, 'moderado')

    def test_con_la_ficha_completa_solo_pregunta_el_peso(self):
        Cliente.objects.filter(pk=self.cliente.pk).update(
            estatura_cm=165, nivel_actividad='moderado'
        )
        self.assertIn('kilos', self._paso(conversacion.CALORIAS).texto)
        final = self._paso('70')
        self.assertIn('mantenerte', final.texto)
        self.assertIn('165 cm', final.texto)

    def test_el_numero_fuera_de_rango_se_rechaza(self):
        self._paso(conversacion.CALORIAS)
        r = self._paso('700')
        self.assertIn('entre 25 y 300', r.texto)
        self.assertEqual(
            ClienteTelegram.objects.get(pk=self.enlace.pk).paso, conversacion.PASO_PESO
        )

    def test_lo_que_no_es_numero_se_rechaza(self):
        self._paso(conversacion.CALORIAS)
        self.assertIn('numero', self._paso('mucho').texto)

    def test_acepta_coma_decimal(self):
        self._paso(conversacion.CALORIAS)
        self.assertIn('centimetros', self._paso('70,5').texto)

    def test_cancelar_corta_el_flujo(self):
        self._paso(conversacion.CALORIAS)
        r = self._paso(conversacion.CANCELAR)
        self.assertIn('lo dejamos', r.texto)
        self.assertEqual(ClienteTelegram.objects.get(pk=self.enlace.pk).paso, '')

    def test_pregunta_lo_que_falta_en_la_ficha(self):
        """Sin sexo ni fecha de nacimiento hacen falta dos preguntas mas."""
        Cliente.objects.filter(pk=self.cliente.pk).update(
            sexo='', fecha_nacimiento=None
        )
        self.assertIn('kilos', self._paso(conversacion.CALORIAS).texto)
        self.assertIn('centimetros', self._paso('70').texto)
        self.assertIn('anos tienes', self._paso('165').texto)
        self.assertIn('hombre o mujer', self._paso('30').texto)
        self.assertIn('dias por semana', self._paso('Mujer').texto)
        self.assertIn('mantenerte', self._paso('Nada o casi nada').texto)

    def test_la_formula_da_el_valor_conocido(self):
        """Mifflin-St Jeor para mujer de 30 anos, 70 kg y 165 cm, sedentaria."""
        self._paso(conversacion.CALORIAS)
        self._paso('70')
        self._paso('165')
        texto = self._paso('Nada o casi nada').texto
        # 10*70 + 6.25*165 - 5*30 - 161 = 1420 en reposo; x1.2 = 1704
        self.assertIn('1420', texto)
        self.assertIn('1704', texto)


class WebhookTest(BaseBotTest):
    def url(self, slug=None):
        return reverse('bot:webhook', args=[slug or self.gym.slug])

    def enviar(self, texto, secreto=None, slug=None):
        return self.client.post(
            self.url(slug),
            data=json.dumps({'message': {'chat': {'id': CHAT}, 'text': texto}}),
            content_type='application/json',
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=(
                self.bot.secreto if secreto is None else secreto
            ),
        )

    def test_sin_secreto_no_responde(self):
        self.assertEqual(self.enviar('hola', secreto='').status_code, 403)

    def test_con_secreto_equivocado_no_responde(self):
        self.assertEqual(self.enviar('hola', secreto='otro').status_code, 403)

    def test_gimnasio_inexistente(self):
        self.assertEqual(self.enviar('hola', slug='no-existe').status_code, 404)

    def test_get_no_se_atiende(self):
        self.assertEqual(self.client.get(self.url()).status_code, 405)

    @mock.patch('bot.views.telegram.enviar')
    def test_mensaje_valido_responde_por_telegram(self, enviar):
        self.assertEqual(self.enviar('/start').status_code, 200)
        enviar.assert_called_once()
        self.assertIn('codigo de acceso', enviar.call_args.args[2])

    @mock.patch('bot.views.telegram.enviar', side_effect=RuntimeError('boom'))
    def test_un_fallo_nuestro_no_hace_que_telegram_reintente(self, enviar):
        """Un 500 haria que Telegram reenvie el mismo mensaje en bucle."""
        with self.assertLogs('bot.views', level='ERROR'):
            self.assertEqual(self.enviar('/start').status_code, 200)

    def test_bot_desactivado_no_atiende(self):
        BotTelegram.objects.filter(pk=self.bot.pk).update(activo=False)
        self.assertEqual(self.enviar('hola').status_code, 404)


class PanelTest(BaseBotTest):
    def setUp(self):
        from django.contrib.auth.models import Group

        from core.roles import ADMINISTRADOR

        self.usuario = User.objects.create_user(
            username='admin', password='pass12345',
            gym=self.gym, sucursal=self.sucursal,
        )
        self.usuario.groups.add(Group.objects.get(name=ADMINISTRADOR))
        self.client.force_login(self.usuario)

    def test_genera_el_codigo_desde_la_ficha(self):
        r = self.client.post(
            reverse('bot:codigo_vinculacion', args=[self.cliente.pk]), follow=True
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(CodigoVinculacion.objects.filter(cliente=self.cliente).exists())

    def test_no_genera_codigo_para_un_cliente_de_otro_gimnasio(self):
        otro = Gym.objects.create(nombre='Otro', plan=Plan.objects.get(nombre='Basico'))
        ajeno = Cliente.objects.create(
            gym=otro, sucursal=Sucursal.objects.get(gym=otro), nombre='Ajeno'
        )
        r = self.client.post(reverse('bot:codigo_vinculacion', args=[ajeno.pk]))
        self.assertEqual(r.status_code, 404)

    def test_la_ficha_captura_lo_que_necesita_la_calculadora(self):
        r = self.client.post(
            reverse('clientes:cliente_update', args=[self.cliente.pk]),
            {
                'nombre': 'Ana Torres', 'sucursal': self.sucursal.pk,
                'sexo': 'F', 'fecha_nacimiento': '1996-01-01',
                'estatura_cm': '165', 'nivel_actividad': 'moderado',
                'peso_kg': '70.5',
            },
        )
        self.assertEqual(r.status_code, 302)

        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.estatura_cm, 165)
        self.assertEqual(self.cliente.nivel_actividad, 'moderado')
        self.assertEqual(
            float(MedidaCorporal.objects.get(cliente=self.cliente).peso_kg), 70.5
        )

    def test_reeditar_la_ficha_no_llena_el_historico(self):
        datos = {
            'nombre': 'Ana Torres', 'sucursal': self.sucursal.pk, 'peso_kg': '70',
        }
        url = reverse('clientes:cliente_update', args=[self.cliente.pk])
        self.client.post(url, datos)
        self.client.post(url, {**datos, 'peso_kg': '71'})

        medidas = MedidaCorporal.objects.filter(cliente=self.cliente)
        self.assertEqual(medidas.count(), 1)
        self.assertEqual(float(medidas.first().peso_kg), 71.0)

    def test_la_configuracion_carga(self):
        r = self.client.get(reverse('bot:configuracion'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'BotFather')

    def test_conectar_sin_token_avisa(self):
        BotTelegram.objects.filter(pk=self.bot.pk).update(token='')
        r = self.client.post(reverse('bot:conectar'), follow=True)
        self.assertContains(r, 'BotFather')
