"""
El lector de huellas, detras de una interfaz chica.

Cada fabricante trae su SDK y su formato de plantilla, asi que todo lo que
depende de la marca vive aqui y en ningun otro lado. El resto del sistema solo
conoce tres verbos: capturar, comparar e identificar.

Mientras no hay lector fisico se usa LectorFalso, que hace lo mismo con
plantillas inventadas. No es solo un tapaobjetos para desarrollar: es lo que
permite probar el acceso por huella en automatico, cosa que con hardware real
no se podria correr nunca.

Para agregar un lector de verdad se escribe una clase mas en este archivo (o en
uno propio) y se apunta LECTOR_HUELLAS a ella. Nada mas cambia.
"""

import hashlib
import random

from django.conf import settings
from django.utils.module_loading import import_string

#: Debajo de esto dos capturas se consideran de dedos distintos. Los SDK dan
#: puntajes en escalas propias; la traduccion a 0-100 la hace cada lector para
#: que este umbral signifique lo mismo con cualquier marca.
UMBRAL = 60

#: Una captura por debajo de esto no se guarda: enrolar una huella mala regresa
#: en forma de socio que no puede entrar y no sabe por que.
CALIDAD_MINIMA = 60


class ErrorDeLector(Exception):
    """El lector no esta, no responde o no logro leer el dedo."""


class Captura:
    """Lo que devuelve el sensor: la plantilla y que tan buena salio."""

    def __init__(self, plantilla, calidad):
        self.plantilla = plantilla
        self.calidad = calidad

    @property
    def sirve(self):
        return self.calidad >= CALIDAD_MINIMA


class Lector:
    """Interfaz que tiene que cumplir cualquier lector."""

    nombre = 'generico'

    def capturar(self):
        """Lee el dedo que este sobre el sensor. Devuelve una Captura."""
        raise NotImplementedError

    def comparar(self, plantilla_a, plantilla_b):
        """Puntaje de parecido de 0 a 100 entre dos plantillas."""
        raise NotImplementedError

    def identificar(self, plantilla, candidatas, umbral=UMBRAL):
        """
        Busca de quien es la huella entre las candidatas (comparacion 1:N).

        `candidatas` son pares (identificador, plantilla). Devuelve el par
        (identificador, puntaje) del mejor parecido que pase el umbral, o
        (None, mejor_puntaje) si ninguno lo pasa.

        Se recorre todo en vez de cortar en el primero que pase: si dos socios
        dan puntaje suficiente, el que gana debe ser el que se parece mas, no
        el que estaba antes en la lista.
        """
        mejor_id, mejor_puntaje = None, 0
        for identificador, candidata in candidatas:
            puntaje = self.comparar(plantilla, candidata)
            if puntaje > mejor_puntaje:
                mejor_id, mejor_puntaje = identificador, puntaje
        if mejor_puntaje < umbral:
            return None, mejor_puntaje
        return mejor_id, mejor_puntaje


#: Quien tiene el dedo puesto en el sensor de mentiras. Vive a nivel de modulo
#: y no en la instancia porque el lector se construye dentro de la vista: las
#: pruebas no lo tienen a la mano para configurarlo.
_PRESENTADO = None
_CALIDAD = 90


def presentar(dedo, calidad=90):
    """Simula que alguien pone el dedo en el sensor. Solo con LectorFalso."""
    global _PRESENTADO, _CALIDAD
    _PRESENTADO, _CALIDAD = dedo, calidad


def retirar():
    """Deja el sensor vacio."""
    global _PRESENTADO
    _PRESENTADO = None


class LectorFalso(Lector):
    """
    Lector de mentiras para desarrollo y pruebas.

    La plantilla es el hash de un dedo imaginario mas ruido, que es como se
    porta un sensor de verdad: el mismo dedo nunca da dos lecturas identicas.
    Comparar cuenta cuantos bytes coinciden, asi que el mismo dedo saca
    puntaje alto y otro dedo saca bajo, sin llegar nunca al 100.
    """

    nombre = 'falso'
    TAMANO = 64

    def __init__(self, dedo=None, calidad=None, ruido=6):
        self._dedo = dedo
        self._calidad = calidad
        self.ruido = ruido
        self._azar = random.Random()

    @property
    def dedo(self):
        return self._dedo if self._dedo is not None else _PRESENTADO

    @property
    def calidad(self):
        return self._calidad if self._calidad is not None else _CALIDAD

    def plantilla_de(self, dedo):
        """La huella ideal de un dedo, sin el ruido de la lectura."""
        base = hashlib.sha256(str(dedo).encode()).digest()
        return (base * (self.TAMANO // len(base) + 1))[:self.TAMANO]

    def capturar(self):
        if self.dedo is None:
            raise ErrorDeLector('No hay ningun dedo sobre el sensor.')
        plantilla = bytearray(self.plantilla_de(self.dedo))
        # Ensuciar unos bytes imita que dos lecturas del mismo dedo difieren.
        for _ in range(self.ruido):
            plantilla[self._azar.randrange(self.TAMANO)] = self._azar.randrange(256)
        return Captura(bytes(plantilla), self.calidad)

    def comparar(self, plantilla_a, plantilla_b):
        if not plantilla_a or not plantilla_b:
            return 0
        a, b = bytes(plantilla_a), bytes(plantilla_b)
        if len(a) != len(b):
            return 0
        iguales = sum(1 for x, y in zip(a, b) if x == y)
        return round(iguales * 100 / len(a))


def obtener_lector():
    """
    El lector configurado. Por omision el falso, para que el sistema arranque
    en cualquier maquina sin hardware conectado.
    """
    ruta = getattr(settings, 'LECTOR_HUELLAS', None)
    if not ruta:
        return LectorFalso()
    return import_string(ruta)()
