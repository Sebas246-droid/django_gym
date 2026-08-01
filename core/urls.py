from django.http import JsonResponse
from django.urls import path

from core import views


def salud(request):
    """Healthcheck para Railway: responde sin tocar la base de datos."""
    return JsonResponse({'status': 'ok'})


app_name = 'core'

urlpatterns = [
    path('salud/', salud, name='salud'),
    path('', views.InicioPublicoView.as_view(), name='inicio'),
    path('g/<slug:slug>/', views.LandingView.as_view(), name='landing'),
    path('tablero/', views.DashboardView.as_view(), name='dashboard'),

    # Sitio publico del gym
    path('sitio/', views.SitioUpdateView.as_view(), name='sitio'),
    path('sitio/imagen/', views.SitioImagenCreateView.as_view(), name='sitio_imagen_create'),
    path(
        'sitio/imagen/<int:pk>/quitar/',
        views.SitioImagenDeleteView.as_view(),
        name='sitio_imagen_delete',
    ),
    path(
        'sitio/membresias/',
        views.SitioMembresiasView.as_view(),
        name='sitio_membresias',
    ),

    # Panel SaaS
    path('planes/', views.PlanListView.as_view(), name='plan_list'),
    path('planes/nuevo/', views.PlanCreateView.as_view(), name='plan_create'),
    path('planes/<int:pk>/editar/', views.PlanUpdateView.as_view(), name='plan_update'),
    path('gimnasios/', views.GymListView.as_view(), name='gym_list'),
    path('gimnasios/nuevo/', views.GymCreateView.as_view(), name='gym_create'),
    path('gimnasios/<int:pk>/editar/', views.GymUpdateView.as_view(), name='gym_update'),

    # Sucursales
    path('sucursales/', views.SucursalListView.as_view(), name='sucursal_list'),
    path('sucursales/nueva/', views.SucursalCreateView.as_view(), name='sucursal_create'),
    path(
        'sucursales/<int:pk>/editar/',
        views.SucursalUpdateView.as_view(),
        name='sucursal_update',
    ),
    path(
        'sucursales/<int:pk>/baja/',
        views.SucursalDeleteView.as_view(),
        name='sucursal_delete',
    ),
]
