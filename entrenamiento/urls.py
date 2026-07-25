from django.urls import path

from entrenamiento import views

app_name = 'entrenamiento'

urlpatterns = [
    path('', views.EntrenamientoListView.as_view(), name='list'),
    path('nuevo/', views.EntrenamientoCreateView.as_view(), name='create'),
    path('<int:pk>/editar/', views.EntrenamientoUpdateView.as_view(), name='update'),
    path('<int:pk>/baja/', views.EntrenamientoDeleteView.as_view(), name='delete'),
]
