from django.contrib import admin

from inventario.models import (
    CategoriaProducto,
    Compra,
    CompraDetalle,
    InventarioSucursal,
    Producto,
    Proveedor,
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


@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'gym', 'telefono', 'activo']
    list_filter = ['gym', 'activo']


class CompraDetalleInline(admin.TabularInline):
    model = CompraDetalle
    extra = 0


@admin.register(Compra)
class CompraAdmin(admin.ModelAdmin):
    list_display = ['id', 'gym', 'proveedor', 'sucursal', 'fecha', 'total', 'estado']
    list_filter = ['gym', 'sucursal', 'estado']
    inlines = [CompraDetalleInline]
