from django.urls import path

from accounts import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.GymLoginView.as_view(), name='login'),
    path('logout/', views.GymLogoutView.as_view(), name='logout'),
    path('perfil/', views.PerfilView.as_view(), name='perfil'),

    path('usuarios/', views.UsuarioListView.as_view(), name='usuario_list'),
    path('usuarios/nuevo/', views.UsuarioCreateView.as_view(), name='usuario_create'),
    path(
        'usuarios/<int:pk>/editar/',
        views.UsuarioUpdateView.as_view(),
        name='usuario_update',
    ),
    path(
        'usuarios/<int:pk>/estado/',
        views.UsuarioToggleView.as_view(),
        name='usuario_toggle',
    ),
    path(
        'usuarios/<int:pk>/contrasena/',
        views.UsuarioPasswordView.as_view(),
        name='usuario_password',
    ),
    path(
        'gimnasios/<int:gym_pk>/administrador/',
        views.AdminGymCreateView.as_view(),
        name='admin_gym_create',
    ),
]
