"""Pruebas del modulo de staff."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from core.models import Gym, Plan, Sucursal
from core.roles import ADMINISTRADOR, RECEPCION

User = get_user_model()


class StaffTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('init_saas')
        cls.gym = Gym.objects.create(
            nombre='Iron House', plan=Plan.objects.get(nombre='Pro')
        )
        cls.sucursal = Sucursal.objects.get(gym=cls.gym, nombre='Principal')
        cls.admin = User.objects.create_user(
            username='admin', password='pass12345',
            gym=cls.gym, sucursal=cls.sucursal,
        )
        cls.admin.groups.add(Group.objects.get(name=ADMINISTRADOR))

    def setUp(self):
        self.client.force_login(self.admin)

    def crear_integrante(self, username='ana'):
        usuario = User.objects.create_user(
            username=username, password='vieja-clave-123',
            gym=self.gym, sucursal=self.sucursal,
        )
        usuario.groups.add(Group.objects.get(name=RECEPCION))
        return usuario

    def test_alta_con_usuario_y_contrasena_para_entrar(self):
        respuesta = self.client.post(
            reverse('accounts:usuario_create'),
            {
                'username': 'recepcion1',
                'first_name': 'Ana',
                'last_name': 'Perez',
                'email': 'ana@test.com',
                'telefono': '5512345678',
                'sucursal': self.sucursal.pk,
                'rol': Group.objects.get(name=RECEPCION).pk,
                'password1': 'clave-segura-123',
                'password2': 'clave-segura-123',
            },
        )
        self.assertEqual(respuesta.status_code, 302)

        self.client.logout()
        entro = self.client.login(username='recepcion1', password='clave-segura-123')
        self.assertTrue(entro)

    def test_el_admin_restablece_la_contrasena(self):
        integrante = self.crear_integrante()

        respuesta = self.client.post(
            reverse('accounts:usuario_password', args=[integrante.pk]),
            {'password1': 'nueva-clave-456', 'password2': 'nueva-clave-456'},
        )
        self.assertEqual(respuesta.status_code, 302)

        self.client.logout()
        self.assertTrue(self.client.login(username='ana', password='nueva-clave-456'))

    def test_contrasenas_distintas_no_pasan(self):
        integrante = self.crear_integrante()

        self.client.post(
            reverse('accounts:usuario_password', args=[integrante.pk]),
            {'password1': 'nueva-clave-456', 'password2': 'otra-cosa-789'},
        )

        self.client.logout()
        self.assertTrue(self.client.login(username='ana', password='vieja-clave-123'))

    def test_no_se_toca_al_staff_de_otro_gimnasio(self):
        otro_gym = Gym.objects.create(
            nombre='Otro', plan=Plan.objects.get(nombre='Basico')
        )
        ajeno = User.objects.create_user(
            username='ajeno', password='clave-ajena-123', gym=otro_gym
        )

        respuesta = self.client.post(
            reverse('accounts:usuario_password', args=[ajeno.pk]),
            {'password1': 'hackeada-123', 'password2': 'hackeada-123'},
        )

        self.assertEqual(respuesta.status_code, 404)
        self.client.logout()
        self.assertTrue(self.client.login(username='ajeno', password='clave-ajena-123'))

    def test_recepcion_no_administra_al_staff(self):
        integrante = self.crear_integrante()
        self.client.force_login(integrante)

        listado = self.client.get(reverse('accounts:usuario_list'))

        self.assertIn(listado.status_code, (302, 403))
