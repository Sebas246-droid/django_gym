"""
La migracion que le pone sucursal a las ventas de membresia viejas.

Es la unica pieza de todo esto que va a tocar los datos reales del gimnasio en
Railway, y corre sola en el deploy. Se prueba de verdad: se retrocede la base
al estado anterior, se meten registros como los que ya existen alla, y se
avanza. Probar solo el codigo Python de la funcion no serviria: lo que puede
salir mal es el paso completo sobre una tabla con datos.
"""

from datetime import date

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

ANTES = [('clientes', '0009_huella')]
DESPUES = [('clientes', '0011_rellenar_sucursal_de_membresias')]


class MigracionDeSucursalTest(TransactionTestCase):
    def tearDown(self):
        # Dejar la base al dia: si no, las pruebas que corran despues se
        # encuentran con una tabla sin la columna.
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(DESPUES)
        super().tearDown()

    def retroceder(self):
        executor = MigrationExecutor(connection)
        executor.migrate(ANTES)
        executor.loader.build_graph()
        return executor.loader.project_state(ANTES).apps

    def avanzar(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(DESPUES)
        return executor.loader.project_state(DESPUES).apps

    def montar(self, apps):
        """Un gimnasio con dos sedes, como el que puede haber en produccion."""
        Gym = apps.get_model('core', 'Gym')
        Plan = apps.get_model('core', 'Plan')
        Sucursal = apps.get_model('core', 'Sucursal')
        User = apps.get_model('accounts', 'User')
        Cliente = apps.get_model('clientes', 'Cliente')
        Membresia = apps.get_model('clientes', 'Membresia')

        plan = Plan.objects.create(nombre='Pro', precio=0)
        gym = Gym.objects.create(nombre='Dos Sedes', plan=plan, slug='dos-sedes')
        centro = Sucursal.objects.create(gym=gym, nombre='Centro')
        norte = Sucursal.objects.create(gym=gym, nombre='Norte')
        cajero = User.objects.create(
            username='beto', password='x', gym=gym, sucursal=norte
        )
        socio = Cliente.objects.create(
            gym=gym, sucursal=centro, nombre='Socio', numero_usuario='1000'
        )
        membresia = Membresia.objects.create(
            gym=gym, nombre='Mensual', precio=600, duracion_dias=30
        )
        return {
            'gym': gym, 'centro': centro, 'norte': norte,
            'cajero': cajero, 'socio': socio, 'membresia': membresia,
        }

    def cobro(self, apps, datos, usuario=None):
        ClienteMembresia = apps.get_model('clientes', 'ClienteMembresia')
        return ClienteMembresia.objects.create(
            gym=datos['gym'],
            cliente=datos['socio'],
            membresia=datos['membresia'],
            usuario=usuario,
            inicio=date(2026, 1, 1),
            fin=date(2026, 1, 31),
            precio=600,
        )

    def test_toma_la_sede_de_quien_cobro(self):
        viejo = self.retroceder()
        datos = self.montar(viejo)
        pk = self.cobro(viejo, datos, usuario=datos['cajero']).pk

        nuevo = self.avanzar()

        ClienteMembresia = nuevo.get_model('clientes', 'ClienteMembresia')
        self.assertEqual(
            ClienteMembresia.objects.get(pk=pk).sucursal_id, datos['norte'].pk
        )

    def test_sin_usuario_cae_a_la_sede_del_socio(self):
        """Cobros viejos cargados a mano o migrados: no tienen usuario."""
        viejo = self.retroceder()
        datos = self.montar(viejo)
        pk = self.cobro(viejo, datos, usuario=None).pk

        nuevo = self.avanzar()

        ClienteMembresia = nuevo.get_model('clientes', 'ClienteMembresia')
        self.assertEqual(
            ClienteMembresia.objects.get(pk=pk).sucursal_id, datos['centro'].pk
        )

    def test_no_truena_con_la_tabla_vacia(self):
        """El caso de un gimnasio recien dado de alta."""
        self.retroceder()

        nuevo = self.avanzar()

        ClienteMembresia = nuevo.get_model('clientes', 'ClienteMembresia')
        self.assertEqual(ClienteMembresia.objects.count(), 0)

    def test_aguanta_un_volumen_parecido_al_de_un_gimnasio_con_anos(self):
        """
        El relleno va en bloques; con 1200 registros se cruza mas de una vez el
        corte de 500 y se nota si el bloqueo esta mal puesto.
        """
        viejo = self.retroceder()
        datos = self.montar(viejo)
        ClienteMembresia = viejo.get_model('clientes', 'ClienteMembresia')
        ClienteMembresia.objects.bulk_create([
            ClienteMembresia(
                gym=datos['gym'], cliente=datos['socio'],
                membresia=datos['membresia'], usuario=datos['cajero'],
                inicio=date(2026, 1, 1), fin=date(2026, 1, 31), precio=600,
            )
            for _ in range(1200)
        ])

        nuevo = self.avanzar()

        Nueva = nuevo.get_model('clientes', 'ClienteMembresia')
        self.assertEqual(Nueva.objects.count(), 1200)
        self.assertEqual(Nueva.objects.filter(sucursal__isnull=True).count(), 0)
        self.assertEqual(
            Nueva.objects.filter(sucursal_id=datos['norte'].pk).count(), 1200
        )
