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

    path(
        'stock/<int:pk>/ajustar/',
        views.InventarioUpdateView.as_view(),
        name='inventario_update',
    ),

    path('movimientos/', views.MovimientoListView.as_view(), name='movimiento_list'),
    path(
        'movimientos/nuevo/',
        views.MovimientoCreateView.as_view(),
        name='movimiento_create',
    ),
]
