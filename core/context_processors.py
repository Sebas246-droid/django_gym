from core.roles import es_admin, es_entrenador, es_recepcion

# Que entrada del menu se ilumina segun la url actual
MENU_POR_VISTA = {
    'core:dashboard': 'dashboard',
    'core:sitio': 'sitio',
    'core:sitio_imagen_create': 'sitio',
    'core:sitio_imagen_delete': 'sitio',
    'core:plan_list': 'planes',
    'core:plan_create': 'planes',
    'core:plan_update': 'planes',
    'core:gym_list': 'saas',
    'core:gym_create': 'saas',
    'core:gym_update': 'saas',
    'clientes:checkin': 'checkin',
    'clientes:asistencia_registrar': 'checkin',
    'clientes:asistencia_entrenamiento': 'checkin',
    'ventas:pos': 'pos',
    'ventas:pos_agregar': 'pos',
    'ventas:pos_linea': 'pos',
    'ventas:pos_cobrar': 'pos',
    'ventas:pos_cancelar': 'pos',
}

MENU_POR_APP = {
    'clientes': 'clientes',
    'entrenamiento': 'entrenamientos',
    'inventario': 'inventario',
    'ventas': 'ventas',
    'accounts': 'staff',
    'core': 'sucursales',
}


def _menu_activo(request):
    coincidencia = getattr(request, 'resolver_match', None)
    if not coincidencia:
        return ''
    ruta = coincidencia.view_name
    if ruta in MENU_POR_VISTA:
        return MENU_POR_VISTA[ruta]
    if coincidencia.url_name and coincidencia.url_name.startswith('membresia'):
        return 'membresias'
    return MENU_POR_APP.get(coincidencia.app_name, '')


def gym_context(request):
    """Datos del gym disponibles en todas las plantillas."""
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {}
    return {
        'gym_actual': user.gym,
        'sucursal_actual': user.sucursal,
        'es_admin': es_admin(user),
        'es_recepcion': es_recepcion(user),
        'es_entrenador': es_entrenador(user),
        'menu': _menu_activo(request),
    }
