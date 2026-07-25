from django.contrib import admin

from entrenamiento.models import Entrenamiento


@admin.register(Entrenamiento)
class EntrenamientoAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'gym', 'activo', 'created_at']
    list_filter = ['gym', 'activo']
    search_fields = ['nombre']
