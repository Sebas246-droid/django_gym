from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import Group
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import (
    CreateView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)

from accounts.forms import LoginForm, PasswordForm, UsuarioForm, UsuarioUpdateForm
from accounts.models import User
from core.mixins import AdminRequiredMixin, GymRequiredMixin, SuperUserRequiredMixin
from core.models import Gym, Sucursal
from core.roles import ADMINISTRADOR


class GymLoginView(LoginView):
    template_name = 'accounts/login.html'
    authentication_form = LoginForm
    redirect_authenticated_user = True


class GymLogoutView(LogoutView):
    next_page = reverse_lazy('accounts:login')


class PerfilView(LoginRequiredMixin, TemplateView):
    template_name = 'accounts/perfil.html'


class UsuarioListView(AdminRequiredMixin, GymRequiredMixin, ListView):
    model = User
    template_name = 'accounts/usuario_list.html'
    context_object_name = 'usuarios'

    def get_queryset(self):
        return (
            User.objects.filter(gym=self.request.user.gym)
            .select_related('sucursal')
            .prefetch_related('groups')
            .order_by('-is_active', 'username')
        )


class UsuarioCreateView(AdminRequiredMixin, GymRequiredMixin, CreateView):
    model = User
    form_class = UsuarioForm
    template_name = 'core/form.html'
    success_url = reverse_lazy('accounts:usuario_list')
    extra_context = {'titulo': 'Nuevo usuario'}

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['gym'] = self.request.user.gym
        return kwargs

    def form_valid(self, form):
        gym = self.request.user.gym
        if not gym.puede_crear_usuario():
            messages.error(
                self.request,
                f'Tu plan {gym.plan.nombre} permite {gym.plan.usuarios_max} usuario(s).',
            )
            return redirect('accounts:usuario_list')
        messages.success(self.request, 'Usuario creado. Envia las credenciales.')
        return super().form_valid(form)


class UsuarioUpdateView(AdminRequiredMixin, GymRequiredMixin, UpdateView):
    model = User
    form_class = UsuarioUpdateForm
    template_name = 'core/form.html'
    success_url = reverse_lazy('accounts:usuario_list')
    extra_context = {'titulo': 'Editar usuario'}

    def get_queryset(self):
        return User.objects.filter(gym=self.request.user.gym)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['gym'] = self.request.user.gym
        return kwargs


class UsuarioPasswordView(AdminRequiredMixin, GymRequiredMixin, FormView):
    """
    El administrador fija la contrasena y se la entrega a la persona.
    No hay correo saliente todavia, asi que se muestra en pantalla una vez.
    """

    form_class = PasswordForm
    template_name = 'accounts/password.html'
    success_url = reverse_lazy('accounts:usuario_list')

    @property
    def usuario(self):
        return get_object_or_404(
            User, pk=self.kwargs['pk'], gym=self.request.user.gym
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['usuario'] = self.usuario
        return ctx

    def form_valid(self, form):
        usuario = self.usuario
        usuario.set_password(form.cleaned_data['password1'])
        usuario.save(update_fields=['password'])
        messages.success(
            self.request,
            f'Contrasena actualizada. Entrega estas credenciales a {usuario}: '
            f'usuario "{usuario.username}", contrasena "{form.cleaned_data["password1"]}".',
        )
        return super().form_valid(form)


class UsuarioToggleView(AdminRequiredMixin, GymRequiredMixin, View):
    """Baja / alta logica del usuario."""

    def post(self, request, pk):
        usuario = get_object_or_404(User, pk=pk, gym=request.user.gym)
        if usuario == request.user:
            messages.error(request, 'No puedes desactivar tu propio usuario.')
        else:
            usuario.is_active = not usuario.is_active
            usuario.save(update_fields=['is_active'])
            estado = 'activado' if usuario.is_active else 'desactivado'
            messages.success(request, f'Usuario {estado}.')
        return redirect('accounts:usuario_list')


class AdminGymCreateView(SuperUserRequiredMixin, CreateView):
    """Paso final del alta de un gimnasio: su usuario Administrador."""

    model = User
    form_class = UsuarioForm
    template_name = 'core/form.html'
    success_url = reverse_lazy('core:gym_list')
    extra_context = {'titulo': 'Crear usuario administrador del gimnasio'}

    @property
    def gym(self):
        return get_object_or_404(Gym, pk=self.kwargs['gym_pk'])

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['gym'] = self.gym
        return kwargs

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['rol'].initial = Group.objects.filter(name=ADMINISTRADOR).first()
        if not form.initial.get('sucursal'):
            principal = Sucursal.objects.filter(gym=self.gym, activo=True).first()
            form.fields['sucursal'].initial = principal
        return form

    def form_valid(self, form):
        messages.success(
            self.request, 'Administrador creado. Ya puedes enviarle sus credenciales.'
        )
        return super().form_valid(form)
