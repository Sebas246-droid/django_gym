"""
Le pone sucursal a las ventas de membresia que ya estaban en la base.

No hay forma de saber con certeza donde se cobro cada una: la columna no
existia. Se usa la mejor pista disponible, en este orden:

  1. La sucursal de quien la cobro. Es la mas cercana a la verdad, aunque a esa
     persona la hayan cambiado de sede despues.
  2. La sucursal del socio, cuando la venta no tiene usuario (las que nacieron
     desde el punto de venta viejo o se cargaron a mano).

Se recorre por gimnasio y en bloques para no traerse toda la tabla a memoria.
Un gimnasio de una sola sucursal, que es el caso de casi todos, queda con todo
apuntando a esa unica sede, que es exactamente lo correcto.
"""

from django.db import migrations


def rellenar(apps, schema_editor):
    ClienteMembresia = apps.get_model('clientes', 'ClienteMembresia')

    pendientes = ClienteMembresia.objects.filter(sucursal__isnull=True).select_related(
        'usuario', 'cliente'
    )
    por_actualizar = []
    for venta in pendientes.iterator(chunk_size=500):
        sucursal_id = (
            getattr(venta.usuario, 'sucursal_id', None)
            or getattr(venta.cliente, 'sucursal_id', None)
        )
        if not sucursal_id:
            continue
        venta.sucursal_id = sucursal_id
        por_actualizar.append(venta)
        if len(por_actualizar) >= 500:
            ClienteMembresia.objects.bulk_update(por_actualizar, ['sucursal'])
            por_actualizar.clear()

    if por_actualizar:
        ClienteMembresia.objects.bulk_update(por_actualizar, ['sucursal'])


def vaciar(apps, schema_editor):
    """
    Volver atras deja la columna en nulo. No se pierde nada real: antes de esta
    migracion el dato no existia.
    """
    ClienteMembresia = apps.get_model('clientes', 'ClienteMembresia')
    ClienteMembresia.objects.update(sucursal=None)


class Migration(migrations.Migration):

    dependencies = [
        ('clientes', '0010_clientemembresia_sucursal'),
    ]

    operations = [
        migrations.RunPython(rellenar, vaciar),
    ]
