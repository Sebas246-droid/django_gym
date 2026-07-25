from django.contrib import admin

from core.models import Gym, GymImagen, Plan, Sucursal


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'precio', 'usuarios_max', 'clientes_max',
                    'sucursales_max', 'activo']
    list_filter = ['activo']


@admin.register(Gym)
class GymAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'plan', 'moneda', 'fecha_alta', 'activo']
    list_filter = ['activo', 'plan']
    search_fields = ['nombre', 'email']
    prepopulated_fields = {'slug': ('nombre',)}


@admin.register(Sucursal)
class SucursalAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'gym', 'responsable', 'telefono', 'tiene_mapa', 'activo']
    list_filter = ['gym', 'activo']
    search_fields = ['nombre']


@admin.register(GymImagen)
class GymImagenAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'gym', 'orden', 'activo']
    list_filter = ['gym', 'activo']
