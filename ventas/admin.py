from django.contrib import admin

from ventas.models import Venta, VentaDetalle


class VentaDetalleInline(admin.TabularInline):
    model = VentaDetalle
    extra = 0


@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display = ['id', 'gym', 'sucursal', 'cliente', 'fecha',
                    'total', 'metodo_pago', 'estado']
    list_filter = ['gym', 'sucursal', 'estado', 'metodo_pago']
    inlines = [VentaDetalleInline]
