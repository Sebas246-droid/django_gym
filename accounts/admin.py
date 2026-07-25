from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from accounts.models import User


@admin.register(User)
class GymUserAdmin(UserAdmin):
    list_display = ['username', 'get_full_name', 'gym', 'sucursal', 'is_active']
    list_filter = ['gym', 'is_active', 'groups']
    fieldsets = UserAdmin.fieldsets + (
        ('GymPilot', {'fields': ('gym', 'sucursal', 'telefono', 'foto')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('GymPilot', {'fields': ('gym', 'sucursal', 'telefono')}),
    )
