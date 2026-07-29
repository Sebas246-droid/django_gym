from django.urls import path

from ventas import pos, views

app_name = 'ventas'

urlpatterns = [
    # Punto de venta
    path('pos/', pos.POSView.as_view(), name='pos'),
    path('pos/agregar/<int:pk>/', pos.AgregarView.as_view(), name='pos_agregar'),
    path(
        'pos/agregar-membresia/<int:pk>/',
        pos.AgregarMembresiaView.as_view(),
        name='pos_agregar_membresia',
    ),
    path('pos/linea/<int:pk>/', pos.LineaView.as_view(), name='pos_linea'),
    path('pos/cobrar/', pos.CobrarView.as_view(), name='pos_cobrar'),
    path('pos/cancelar/', pos.CancelarView.as_view(), name='pos_cancelar'),

    path('', views.VentaListView.as_view(), name='venta_list'),
    path('nueva/', views.VentaCreateView.as_view(), name='venta_create'),
    path('<int:pk>/', views.VentaDetailView.as_view(), name='venta_detail'),
    path(
        '<int:pk>/detalle/',
        views.VentaDetalleCreateView.as_view(),
        name='venta_detalle_create',
    ),
    path(
        '<int:pk>/detalle/<int:detalle_pk>/eliminar/',
        views.VentaDetalleDeleteView.as_view(),
        name='venta_detalle_delete',
    ),
    path(
        '<int:pk>/confirmar/', views.VentaConfirmarView.as_view(), name='venta_confirmar'
    ),
]
