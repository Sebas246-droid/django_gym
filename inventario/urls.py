from django.urls import path

from inventario import views

app_name = 'inventario'

urlpatterns = [
    path('categorias/', views.CategoriaListView.as_view(), name='categoria_list'),
    path('categorias/nueva/', views.CategoriaCreateView.as_view(), name='categoria_create'),
    path(
        'categorias/<int:pk>/editar/',
        views.CategoriaUpdateView.as_view(),
        name='categoria_update',
    ),
    path(
        'categorias/<int:pk>/baja/',
        views.CategoriaDeleteView.as_view(),
        name='categoria_delete',
    ),

    path('productos/', views.ProductoListView.as_view(), name='producto_list'),
    path('productos/nuevo/', views.ProductoCreateView.as_view(), name='producto_create'),
    path(
        'productos/<int:pk>/editar/',
        views.ProductoUpdateView.as_view(),
        name='producto_update',
    ),
    path(
        'productos/<int:pk>/baja/',
        views.ProductoDeleteView.as_view(),
        name='producto_delete',
    ),

    path('stock/', views.InventarioListView.as_view(), name='inventario_list'),
    path(
        'stock/<int:pk>/ajustar/',
        views.InventarioUpdateView.as_view(),
        name='inventario_update',
    ),

    path('proveedores/', views.ProveedorListView.as_view(), name='proveedor_list'),
    path(
        'proveedores/nuevo/', views.ProveedorCreateView.as_view(), name='proveedor_create'
    ),
    path(
        'proveedores/<int:pk>/editar/',
        views.ProveedorUpdateView.as_view(),
        name='proveedor_update',
    ),
    path(
        'proveedores/<int:pk>/baja/',
        views.ProveedorDeleteView.as_view(),
        name='proveedor_delete',
    ),

    path('compras/', views.CompraListView.as_view(), name='compra_list'),
    path('compras/nueva/', views.CompraCreateView.as_view(), name='compra_create'),
    path('compras/<int:pk>/', views.CompraDetailView.as_view(), name='compra_detail'),
    path(
        'compras/<int:pk>/detalle/',
        views.CompraDetalleCreateView.as_view(),
        name='compra_detalle_create',
    ),
    path(
        'compras/<int:pk>/detalle/<int:detalle_pk>/eliminar/',
        views.CompraDetalleDeleteView.as_view(),
        name='compra_detalle_delete',
    ),
    path(
        'compras/<int:pk>/confirmar/',
        views.CompraConfirmarView.as_view(),
        name='compra_confirmar',
    ),
]
