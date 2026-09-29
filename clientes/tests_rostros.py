"""
Reconocimiento facial, del lado que se puede comprobar sin una camara.

Lo que corre en el navegador (encender la camara, encontrar la cara, sacar los
128 numeros) no se prueba aqui. Lo que si se prueba es todo lo que decide algo:
a quien se parece un descriptor, que no se pueda enrolar sin firma, que una
cara no se cuele en otro gimnasio y que el kiosco de el mismo veredicto que
tecleando el numero.
"""

import base64
import json
import random

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from clientes import rostros
from clientes.models import (
    Asistencia,
    Cliente,
    ClienteMembresia,
    ConsentimientoRostro,
    Membresia,
    Rostro,
)
from core.models import Gym, Plan, Sucursal
from core.roles import ADMINISTRADOR

User = get_user_model()

#: Un png de 1x1 transparente. Sirve de firma: lo que se prueba es que se exija
#: y se guarde, no que el trazo se parezca a nada.
FIRMA = 'data:image/png;base64,' + base64.b64encode(
    bytes.fromhex(
        '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4'
        '890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082'
    )
).decode()


def cara(semilla, ruido=0.0):
    """
    Un descriptor de mentira, reproducible.

    Con la misma semilla sale la misma cara; con ruido sale la misma persona en
    otra toma, y con otra semilla sale otra persona.
    """
    generador = random.Random(semilla)
    base = [generador.uniform(-1, 1) for _ in range(rostros.LARGO)]
    if not ruido:
        return base
    temblor = random.Random(f'{semilla}-{ruido}')
    return [n + temblor.uniform(-ruido, ruido) for n in base]


class DistanciaEntreCarasTest(TestCase):
    def test_la_misma_cara_queda_cerca_y_otra_lejos(self):
        yo = cara('ana')
        yo_otro_dia = cara('ana', ruido=0.02)
        otra_persona = cara('luis')

        self.assertLess(rostros.distancia(yo, yo_otro_dia), rostros.UMBRAL)
        self.assertGreater(rostros.distancia(yo, otra_persona), rostros.UMBRAL)

    def test_no_se_guarda_cualquier_cosa(self):
        """Llega del navegador: un JSONField traga lo que sea."""
        for basura in ('hola', [1, 2, 3], list('x' * rostros.LARGO), None):
            with self.subTest(basura=str(basura)[:20]):
                with self.assertRaises(rostros.DescriptorInvalido):
                    rostros.limpiar(basura)


class BaseRostroTest(TestCase):
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

    def crear_socio(self, nombre, con_membresia=True):
        socio = Cliente.objects.create(
            gym=self.gym, sucursal=self.sucursal, nombre=nombre
        )
        if con_membresia:
            ClienteMembresia.objects.create(
                gym=self.gym, cliente=socio, membresia=self.membresia,
                inicio=timezone.localdate(), precio=600,
            )
        return socio

    def enrolar(self, socio, semilla, firma=FIRMA, tomas=3):
        return self.client.post(
            reverse('clientes:rostro_enrolar', args=[socio.pk]),
            {
                'firma': firma,
                'descriptores': json.dumps(
                    [cara(semilla, ruido=0.01 * i) for i in range(tomas)]
                ),
            },
        )


class EnrolarRostroTest(BaseRostroTest):
    def test_guarda_las_tomas_y_el_consentimiento(self):
        socio = self.crear_socio('Ana Torres')

        self.enrolar(socio, 'ana')

        self.assertEqual(socio.rostros.count(), 3)
        consentimiento = ConsentimientoRostro.objects.get(cliente=socio)
        self.assertEqual(consentimiento.usuario, self.usuario)
        self.assertTrue(consentimiento.firma.name)

    def test_sin_firma_no_se_captura_nada(self):
        """El rostro es dato sensible: sin consentimiento no se toca."""
        socio = self.crear_socio('Ana Torres')

        self.enrolar(socio, 'ana', firma='')

        self.assertEqual(socio.rostros.count(), 0)
        self.assertFalse(ConsentimientoRostro.objects.filter(cliente=socio).exists())

    def test_se_guarda_el_texto_que_firmo_y_no_una_referencia(self):
        """El aviso puede cambiar manana; lo que firmo, no."""
        socio = self.crear_socio('Ana Torres')

        self.enrolar(socio, 'ana')

        texto = ConsentimientoRostro.objects.get(cliente=socio).texto
        self.assertIn(self.gym.nombre, texto)
        self.assertIn('dato personal sensible', texto)

    def test_una_cara_no_se_puede_enrolar_a_dos_socios(self):
        """Si no, el acceso deja entrar al que la comparacion encuentre primero."""
        primero = self.crear_socio('Ana Torres')
        segundo = self.crear_socio('Ana Gemela')
        self.enrolar(primero, 'ana')

        self.enrolar(segundo, 'ana')

        self.assertEqual(segundo.rostros.count(), 0)

    def test_volver_a_enrolar_reemplaza_las_tomas_viejas(self):
        socio = self.crear_socio('Ana Torres')
        self.enrolar(socio, 'ana')

        self.enrolar(socio, 'ana', tomas=2)

        self.assertEqual(socio.rostros.count(), 2)

    def test_borrar_se_lleva_rostro_y_consentimiento(self):
        """De nada sirve pedir permiso si no se puede retirar."""
        socio = self.crear_socio('Ana Torres')
        self.enrolar(socio, 'ana')

        self.client.post(reverse('clientes:rostro_borrar', args=[socio.pk]))

        self.assertEqual(socio.rostros.count(), 0)
        self.assertFalse(ConsentimientoRostro.objects.filter(cliente=socio).exists())

    def test_no_se_enrola_a_un_socio_de_otro_gimnasio(self):
        otro = Gym.objects.create(
            nombre='Otro', plan=Plan.objects.get(nombre='Basico')
        )
        ajeno = Cliente.objects.create(
            gym=otro, sucursal=Sucursal.objects.get(gym=otro), nombre='Ajeno'
        )

        respuesta = self.enrolar(ajeno, 'ajeno')

        self.assertEqual(respuesta.status_code, 404)
        self.assertEqual(ajeno.rostros.count(), 0)


class EntrarConRostroTest(BaseRostroTest):
    def acceder(self, descriptor):
        self.client.post(
            reverse('clientes:checkin_rostro'),
            {'descriptor': json.dumps(descriptor)},
        )
        return self.client.session['acceso']

    def test_reconoce_al_socio_y_le_marca_la_entrada(self):
        socio = self.crear_socio('Ana Torres')
        self.enrolar(socio, 'ana')

        resultado = self.acceder(cara('ana', ruido=0.03))

        self.assertEqual(resultado['estado'], 'ok')
        self.assertEqual(resultado['nombre'], 'Ana Torres')
        self.assertTrue(Asistencia.objects.filter(cliente=socio).exists())

    def test_a_quien_no_reconoce_lo_manda_al_teclado(self):
        self.enrolar(self.crear_socio('Ana Torres'), 'ana')

        resultado = self.acceder(cara('un-desconocido'))

        self.assertEqual(resultado['estado'], 'invalido')
        self.assertIn('numero', resultado['detalle'])
        self.assertEqual(Asistencia.objects.count(), 0)

    def test_el_veredicto_es_el_mismo_que_tecleando_el_numero(self):
        """Sin membresia no entra, lo reconozca la camara o no."""
        socio = self.crear_socio('Sin Plan', con_membresia=False)
        self.enrolar(socio, 'sinplan')

        resultado = self.acceder(cara('sinplan', ruido=0.02))

        self.assertEqual(resultado['estado'], 'vencida')

    def test_una_cara_de_otro_gimnasio_no_abre_aqui(self):
        """
        Las caras de un gimnasio no se comparan contra las de otro: nadie tiene
        por que entrar donde no esta inscrito.
        """
        otro = Gym.objects.create(
            nombre='Otro', plan=Plan.objects.get(nombre='Basico')
        )
        ajeno = Cliente.objects.create(
            gym=otro, sucursal=Sucursal.objects.get(gym=otro), nombre='Ajeno'
        )
        Rostro.objects.create(gym=otro, cliente=ajeno, descriptor=cara('ajeno'))

        resultado = self.acceder(cara('ajeno', ruido=0.01))

        self.assertEqual(resultado['estado'], 'invalido')
        self.assertEqual(Asistencia.objects.count(), 0)

    def test_un_socio_dado_de_baja_deja_de_pasar(self):
        socio = self.crear_socio('Ya No Viene')
        self.enrolar(socio, 'yanoviene')
        socio.soft_delete()

        resultado = self.acceder(cara('yanoviene', ruido=0.01))

        self.assertEqual(resultado['estado'], 'invalido')

    def test_una_captura_mala_no_tumba_el_kiosco(self):
        resultado = self.acceder('esto no es un descriptor')

        self.assertEqual(resultado['estado'], 'invalido')
        self.assertIn('luz', resultado['mensaje'])
