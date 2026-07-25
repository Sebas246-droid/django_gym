from django.db import migrations


def asignar_numeros(apps, schema_editor):
    """Los clientes que ya existian reciben su numero consecutivo por gym."""
    Cliente = apps.get_model('clientes', 'Cliente')
    contadores = {}
    for cliente in Cliente.objects.filter(numero_usuario='').order_by('gym_id', 'id'):
        if cliente.gym_id not in contadores:
            usados = (
                Cliente.objects.filter(gym_id=cliente.gym_id)
                .exclude(numero_usuario='')
                .values_list('numero_usuario', flat=True)
            )
            numeros = [int(n) for n in usados if n.isdigit()]
            contadores[cliente.gym_id] = max(numeros) if numeros else 999
        contadores[cliente.gym_id] += 1
        cliente.numero_usuario = str(contadores[cliente.gym_id])
        cliente.save(update_fields=['numero_usuario'])


class Migration(migrations.Migration):

    dependencies = [
        ('clientes', '0002_cliente_numero_usuario_alter_cliente_unique_together'),
    ]

    operations = [
        migrations.RunPython(asignar_numeros, migrations.RunPython.noop),
    ]
