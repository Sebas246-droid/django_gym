from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import Group

from accounts.models import User
from core.forms import SinSufijoMixin
from core.models import Sucursal
from core.roles import ROLES


class LoginForm(SinSufijoMixin, AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs['placeholder'] = 'Tu usuario'
        self.fields['password'].widget.attrs['placeholder'] = 'Tu contrasena'


class PasswordForm(SinSufijoMixin, forms.Form):
    """Restablecer la contrasena de alguien del staff."""

    password1 = forms.CharField(
        label='Nueva contrasena', widget=forms.PasswordInput, min_length=8
    )
    password2 = forms.CharField(
        label='Repite la contrasena', widget=forms.PasswordInput
    )

    def clean(self):
        datos = super().clean()
        if datos.get('password1') != datos.get('password2'):
            raise forms.ValidationError('Las dos contrasenas no coinciden.')
        return datos


class UsuarioForm(SinSufijoMixin, UserCreationForm):
    """Alta de usuario dentro de un gym: sucursal + grupo (rol)."""

    rol = forms.ModelChoiceField(
        queryset=Group.objects.filter(name__in=ROLES),
        label='Rol',
    )

    class Meta:
        model = User
        fields = [
            'username',
            'first_name',
            'last_name',
            'email',
            'telefono',
            'foto',
            'sucursal',
        ]

    def __init__(self, *args, gym=None, **kwargs):
        self.gym = gym
        super().__init__(*args, **kwargs)
        self.fields['sucursal'].queryset = Sucursal.objects.filter(
            gym=gym, activo=True
        )
        self.fields['sucursal'].required = True

    def save(self, commit=True):
        user = super().save(commit=False)
        user.gym = self.gym
        if commit:
            user.save()
            user.groups.set([self.cleaned_data['rol']])
        return user


class UsuarioUpdateForm(SinSufijoMixin, forms.ModelForm):
    rol = forms.ModelChoiceField(
        queryset=Group.objects.filter(name__in=ROLES),
        label='Rol',
    )

    class Meta:
        model = User
        fields = [
            'username',
            'first_name',
            'last_name',
            'email',
            'telefono',
            'foto',
            'sucursal',
            'is_active',
        ]

    def __init__(self, *args, gym=None, **kwargs):
        self.gym = gym
        super().__init__(*args, **kwargs)
        self.fields['sucursal'].queryset = Sucursal.objects.filter(
            gym=gym, activo=True
        )
        if self.instance.pk:
            self.fields['rol'].initial = self.instance.groups.first()

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            user.groups.set([self.cleaned_data['rol']])
        return user
