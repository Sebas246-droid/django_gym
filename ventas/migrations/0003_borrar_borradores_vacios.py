"""
Borra los borradores sin una sola linea.

Los dejaba el alta de venta a mano, que creaba la venta vacia antes de saber
que se iba a vender. Se veian en el historial como ventas de 0.00 que no se
podian cobrar. Sin lineas no guardan nada: ni dinero ni movimiento de stock.
"""

from django.db import migrations


def borrar_vacios(apps, schema_editor):
    Venta = apps.get_model('ventas', 'Venta')
    Venta.objects.filter(estado='borrador', detalles__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('ventas', '0002_ventadetalle_membresia_alter_ventadetalle_producto_and_more'),
    ]

    operations = [
        # Hacia atras no hay nada que reponer: eran registros en blanco.
        migrations.RunPython(borrar_vacios, migrations.RunPython.noop),
    ]
