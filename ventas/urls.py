from django.urls import path

from ventas import pos, views

app_name = 'ventas'

urlpatterns = [
    # Punto de venta: la unica forma de cobrar
    path('pos/', pos.POSView.as_view(), name='pos'),
    path('pos/agregar/<int:pk>/', pos.AgregarView.as_view(), name='pos_agregar'),
    path('pos/linea/<int:pk>/', pos.LineaView.as_view(), name='pos_linea'),
    path('pos/cobrar/', pos.CobrarView.as_view(), name='pos_cobrar'),
    path('pos/cancelar/', pos.CancelarView.as_view(), name='pos_cancelar'),

    # Historial, de lectura
    path('', views.VentaListView.as_view(), name='venta_list'),
    path('<int:pk>/', views.VentaDetailView.as_view(), name='venta_detail'),
]
