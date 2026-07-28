from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

urlpatterns = [
    path('admin/', admin.site.urls),
    path('cuentas/', include('accounts.urls')),
    path('bot/', include('bot.urls')),
    path('clientes/', include('clientes.urls')),
    path('entrenamientos/', include('entrenamiento.urls')),
    path('inventario/', include('inventario.urls')),
    path('ventas/', include('ventas.urls')),
    path('', include('core.urls')),
]

# Fotos subidas por los gimnasios. Cuando hay bucket S3/R2 las sirve el bucket
# y esta ruta sobra; sin bucket las tiene que servir Django, tambien con
# DEBUG=False, o las imagenes salen rotas en produccion.
if settings.SERVE_MEDIA:
    urlpatterns += [
        re_path(
            r'^%s(?P<path>.*)$' % settings.MEDIA_URL.lstrip('/'),
            serve,
            {'document_root': settings.MEDIA_ROOT},
        ),
    ]
