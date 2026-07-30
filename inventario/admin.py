from django.contrib import admin

from inventario.models import (
    CategoriaProducto,
    InventarioSucursal,
    Movimiento,
    Producto,
)


@admin.register(CategoriaProducto)
class CategoriaProductoAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'gym', 'activo']
    list_filter = ['gym', 'activo']


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ['codigo', 'nombre', 'gym', 'categoria',
                    'precio_compra', 'precio_venta', 'activo']
    list_filter = ['gym', 'categoria', 'activo']
    search_fields = ['codigo', 'nombre', 'marca']


@admin.register(InventarioSucursal)
class InventarioSucursalAdmin(admin.ModelAdmin):
    list_display = ['producto', 'sucursal', 'stock', 'stock_minimo']
    list_filter = ['sucursal']


@admin.register(Movimiento)
class MovimientoAdmin(admin.ModelAdmin):
    list_display = ['fecha', 'producto', 'sucursal', 'tipo', 'motivo',
                    'cantidad', 'precio', 'usuario']
    list_filter = ['gym', 'sucursal', 'tipo', 'motivo']
    search_fields = ['producto__nombre', 'producto__codigo', 'nota']
    date_hierarchy = 'fecha'
