from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from core.mixins import GymFormMixin, GymQuerysetMixin, SoftDeleteView
from entrenamiento.forms import EntrenamientoForm
from entrenamiento.models import Entrenamiento


class EntrenamientoListView(GymQuerysetMixin, ListView):
    model = Entrenamiento
    template_name = 'entrenamiento/entrenamiento_list.html'
    context_object_name = 'entrenamientos'


class EntrenamientoCreateView(GymFormMixin, CreateView):
    model = Entrenamiento
    form_class = EntrenamientoForm
    template_name = 'core/form.html'
    success_url = reverse_lazy('entrenamiento:list')
    extra_context = {'titulo': 'Nuevo entrenamiento'}


class EntrenamientoUpdateView(GymFormMixin, UpdateView):
    model = Entrenamiento
    form_class = EntrenamientoForm
    template_name = 'core/form.html'
    success_url = reverse_lazy('entrenamiento:list')
    extra_context = {'titulo': 'Editar entrenamiento'}


class EntrenamientoDeleteView(SoftDeleteView):
    model = Entrenamiento
    success_url = reverse_lazy('entrenamiento:list')
