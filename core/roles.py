"""
Roles del sistema. Se usan Groups nativos de Django, sin tablas propias.
"""

ADMINISTRADOR = 'Administrador'
RECEPCION = 'Recepcion - Caja'
ENTRENADOR = 'Entrenador'

ROLES = [ADMINISTRADOR, RECEPCION, ENTRENADOR]


def es_admin(user):
    return user.is_superuser or user.groups.filter(name=ADMINISTRADOR).exists()


def es_recepcion(user):
    return user.groups.filter(name=RECEPCION).exists()


def es_entrenador(user):
    return user.groups.filter(name=ENTRENADOR).exists()
