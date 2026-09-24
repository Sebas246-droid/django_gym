"""
El menu del panel, en un solo sitio.

Vive en Python y no en la plantilla porque se pinta de dos formas: barra
lateral en computadora y barra de abajo en celular y tablet. Tenerlo escrito
dos veces en HTML garantiza que un dia se agregue una pantalla en una forma y
no en la otra.

El reparto es el del oficio, no el de las carpetas del codigo:

- DIARIO es lo que recepcion toca cada turno. Son cuatro porque cuatro es lo
  que cabe en el pulgar de un telefono junto al boton de "Mas", y porque un
  menu de trece entradas obliga a leerlas todas para encontrar una.
- AJUSTES es lo que se configura una vez y se revisa de tanto en tanto. No
  desaparece: se guarda detras de "Mas".
"""

#: url, texto, icono y, si hace falta, quien puede verlo.
#: `clave` es lo que ilumina la entrada; sale de core.context_processors.
DIARIO = [
    {'clave': 'dashboard', 'texto': 'Tablero', 'icono': 'tablero',
     'url': 'core:dashboard'},
    {'clave': 'clientes', 'texto': 'Clientes', 'icono': 'clientes',
     'url': 'clientes:cliente_list'},
    {'clave': 'pos', 'texto': 'Caja', 'icono': 'pos', 'url': 'ventas:pos'},
    {'clave': 'checkin', 'texto': 'Acceso', 'icono': 'acceso',
     'url': 'clientes:checkin'},
]

AJUSTES = [
    {'clave': 'asistencias', 'texto': 'Historial de accesos', 'icono': 'acceso',
     'url': 'clientes:asistencia_list'},
    {'clave': 'membresias', 'texto': 'Membresias', 'icono': 'membresias',
     'url': 'clientes:membresia_list'},
    {'clave': 'inventario', 'texto': 'Inventario', 'icono': 'inventario',
     'url': 'inventario:producto_list'},
    {'clave': 'entrenamientos', 'texto': 'Entrenamientos', 'icono': 'entrenamiento',
     'url': 'entrenamiento:list'},
    {'clave': 'staff', 'texto': 'Staff', 'icono': 'staff',
     'url': 'accounts:usuario_list', 'solo_admin': True},
    {'clave': 'sucursales', 'texto': 'Sucursales', 'icono': 'sucursales',
     'url': 'core:sucursal_list', 'solo_admin': True},
    {'clave': 'sitio', 'texto': 'Sitio web', 'icono': 'sitio',
     'url': 'core:sitio', 'solo_admin': True},
]

#: El panel del SaaS. No es del gimnasio, asi que va aparte y al final.
PLATAFORMA = [
    {'clave': 'saas', 'texto': 'Gimnasios', 'icono': 'gimnasios',
     'url': 'core:gym_list'},
    {'clave': 'planes', 'texto': 'Planes', 'icono': 'planes',
     'url': 'core:plan_list'},
]


def _permitidas(entradas, es_admin):
    return [e for e in entradas if not e.get('solo_admin') or es_admin]


def para(usuario, es_admin):
    """Las listas del menu, ya filtradas por lo que puede ver el usuario."""
    con_gym = bool(getattr(usuario, 'gym_id', None))
    diario = _permitidas(DIARIO, es_admin) if con_gym else []
    ajustes = _permitidas(AJUSTES, es_admin) if con_gym else []
    plataforma = PLATAFORMA if usuario.is_superuser else []
    return {
        'menu_diario': diario,
        'menu_ajustes': ajustes,
        'menu_plataforma': plataforma,
        # Lo que va en la barra de abajo. El super administrador del SaaS no
        # tiene gimnasio, asi que su diario viene vacio y su barra son las
        # pantallas de plataforma. Sin esto se quedaba sin barra y, con ella,
        # sin el unico boton de cerrar sesion que hay en pantalla chica.
        'menu_barra': diario or plataforma,
    }
