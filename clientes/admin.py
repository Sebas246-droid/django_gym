from django.contrib import admin

from clientes.models import Asistencia, Cliente, ClienteMembresia, Membresia


@admin.register(Membresia)
class MembresiaAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'gym', 'precio', 'duracion_dias', 'activo']
    list_filter = ['gym', 'activo']


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'gym', 'sucursal', 'telefono', 'activo']
    list_filter = ['gym', 'sucursal', 'activo']
    search_fields = ['nombre', 'telefono', 'correo']


@admin.register(ClienteMembresia)
class ClienteMembresiaAdmin(admin.ModelAdmin):
    list_display = ['cliente', 'membresia', 'inicio', 'fin', 'estado',
                    'precio', 'metodo_pago', 'usuario']
    list_filter = ['gym', 'estado', 'metodo_pago']


@admin.register(Asistencia)
class AsistenciaAdmin(admin.ModelAdmin):
    list_display = ['cliente', 'tipo', 'fecha_hora', 'sucursal', 'entrenamiento']
    list_filter = ['gym', 'sucursal', 'tipo']
