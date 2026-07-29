from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import DeleteView

from core.roles import es_admin


class GymRequiredMixin(LoginRequiredMixin):
    """
    Toda vista de negocio vive dentro de un gym.
    El super administrador del SaaS (sin gym) no opera aqui.
    """

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.gym_id is None:
            messages.warning(
                request,
                'Tu usuario no pertenece a ningun gimnasio. '
                'Administra el SaaS desde el panel de gimnasios.',
            )
            return redirect('core:gym_list')
        return super().dispatch(request, *args, **kwargs)

    @property
    def gym(self):
        return self.request.user.gym


class GymQuerysetMixin(GymRequiredMixin):
    """Filtra SIEMPRE por gym del usuario. Nunca se mezclan los datos."""

    solo_activos = True

    def get_queryset(self):
        qs = super().get_queryset().filter(gym=self.gym)
        if self.solo_activos:
            qs = qs.filter(activo=True)
        return qs


class GymFormMixin(GymQuerysetMixin):
    """Inyecta el gym en el formulario y en la instancia guardada."""

    #: Aviso al guardar. Las vistas que dan uno mas concreto lo ponen en None,
    #: o se apilan dos mensajes diciendo lo mismo.
    mensaje_exito = 'Registro guardado correctamente.'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['gym'] = self.gym
        return kwargs

    def form_valid(self, form):
        form.instance.gym = self.gym
        if self.mensaje_exito:
            messages.success(self.request, self.mensaje_exito)
        return super().form_valid(form)


class SoftDeleteView(GymQuerysetMixin, DeleteView):
    """Baja logica: activo = False."""

    template_name = 'core/confirm_delete.html'

    def form_valid(self, form):
        self.object = self.get_object()
        self.object.soft_delete()
        messages.success(self.request, 'Registro dado de baja.')
        return redirect(self.get_success_url())


class AdminRequiredMixin(UserPassesTestMixin):
    """Solo Administrador del gym o superusuario."""

    def test_func(self):
        return self.request.user.is_authenticated and es_admin(self.request.user)


class SuperUserRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Panel del SaaS: solo super administrador."""

    login_url = reverse_lazy('accounts:login')

    def test_func(self):
        return self.request.user.is_superuser
