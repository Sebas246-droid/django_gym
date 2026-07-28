from django.urls import path

from bot import views

app_name = 'bot'

urlpatterns = [
    # Publica: la llama Telegram, protegida por el secreto de la cabecera.
    path('webhook/<slug:slug>/', views.webhook, name='webhook'),

    path('configuracion/', views.BotConfigView.as_view(), name='configuracion'),
    path('conectar/', views.BotConectarView.as_view(), name='conectar'),
    path('desconectar/', views.BotDesconectarView.as_view(), name='desconectar'),
    path(
        'codigo/<int:pk>/',
        views.CodigoVinculacionView.as_view(),
        name='codigo_vinculacion',
    ),
]
