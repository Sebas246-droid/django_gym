from django.urls import path

from clientes import views

app_name = 'clientes'

urlpatterns = [
    path('', views.ClienteListView.as_view(), name='cliente_list'),
    path('nuevo/', views.ClienteCreateView.as_view(), name='cliente_create'),
    path('<int:pk>/', views.ClienteDetailView.as_view(), name='cliente_detail'),
    path('<int:pk>/editar/', views.ClienteUpdateView.as_view(), name='cliente_update'),
    path('<int:pk>/baja/', views.ClienteDeleteView.as_view(), name='cliente_delete'),
    path(
        '<int:pk>/credencial/',
        views.ClienteCredencialView.as_view(),
        name='cliente_credencial',
    ),

    path('membresias/', views.MembresiaListView.as_view(), name='membresia_list'),
    path(
        'membresias/nueva/', views.MembresiaCreateView.as_view(), name='membresia_create'
    ),
    path(
        'membresias/<int:pk>/editar/',
        views.MembresiaUpdateView.as_view(),
        name='membresia_update',
    ),
    path(
        'membresias/<int:pk>/baja/',
        views.MembresiaDeleteView.as_view(),
        name='membresia_delete',
    ),

    path(
        'ventas-membresia/',
        views.ClienteMembresiaListView.as_view(),
        name='clientemembresia_list',
    ),
    path(
        'ventas-membresia/nueva/',
        views.ClienteMembresiaCreateView.as_view(),
        name='clientemembresia_create',
    ),
    path(
        'ventas-membresia/<int:pk>/editar/',
        views.ClienteMembresiaUpdateView.as_view(),
        name='clientemembresia_update',
    ),
    path(
        'ventas-membresia/<int:pk>/cancelar/',
        views.ClienteMembresiaCancelarView.as_view(),
        name='clientemembresia_cancelar',
    ),

    path('asistencias/', views.AsistenciaListView.as_view(), name='asistencia_list'),
    path('acceso/', views.CheckinView.as_view(), name='checkin'),
    path(
        'acceso/<int:pk>/registrar/',
        views.AsistenciaRegistrarView.as_view(),
        name='asistencia_registrar',
    ),
    path(
        'acceso/asistencia/<int:pk>/entrenamiento/',
        views.AsistenciaEntrenamientoView.as_view(),
        name='asistencia_entrenamiento',
    ),
]
