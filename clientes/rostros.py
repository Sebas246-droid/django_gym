"""
Reconocimiento facial: comparar descriptores.

El modelo corre en el navegador del kiosco y de ahi sale un descriptor: 128
numeros que describen una cara. Este modulo hace lo unico que se hace en el
servidor, que es buscar a quien se parece.

Se compara aqui y no en el navegador a proposito. Si el navegador decidiera a
quien se parece, bastaria con abrir la consola y mandar el id de cualquier
socio: el kiosco es una tablet en la entrada, no un lugar de confianza. Asi lo
unico que puede mandar es una cara.

Comparar cuesta 128 restas por rostro guardado. Con quinientos socios y tres
tomas cada uno son mil quinientas comparaciones, que en Python tardan menos de
lo que el navegador tardo en encender la camara: no hace falta numpy ni un
indice.
"""

from math import sqrt

#: Cuantos numeros trae un descriptor del modelo que usamos.
LARGO = 128

#: A que distancia dos caras se dan por la misma.
#:
#: El autor del modelo recomienda 0.6 para "reconocer". Aqui se usa 0.5 porque
#: no es lo mismo etiquetar una foto que abrir una puerta: el error caro es
#: dejar entrar a quien no es, y quien no pase siempre puede teclear su numero.
UMBRAL = 0.5


#: Lo que el socio acepta al firmar. Se guarda copia en cada consentimiento,
#: no una referencia: este texto puede cambiar, y lo que hay que poder probar
#: es que firmo esto y no otra cosa.
AVISO = (
    # Cada parrafo en una sola linea: la pantalla lo pinta tal cual, con sus
    # saltos, y los cortes del codigo saldrian como cortes de verdad.
    '{gym} quiere usar tu rostro para que entres sin teclear tu numero.'
    '\n\n'
    'Que se guarda: no tu foto, sino 128 numeros que el sistema calcula a partir'
    ' de ella y con los que no se puede reconstruir tu cara. La foto se procesa'
    ' en la tablet y no se guarda en ningun lado.'
    '\n\n'
    'Para que se usa: unicamente para reconocerte al entrar al gimnasio. Para'
    ' nada mas, y no se comparte con nadie.'
    '\n\n'
    'Cuanto tiempo: mientras seas socio. Si te das de baja o lo pides, se borra.'
    '\n\n'
    'Puedes decir que no: teclear tu numero seguira funcionando siempre, igual'
    ' que hoy. Y puedes arrepentirte cuando quieras, pidiendo en recepcion que'
    ' borren tu rostro.'
    '\n\n'
    'El rostro es un dato personal sensible. Al firmar autorizas expresamente a'
    ' {gym} a tratarlo en los terminos de arriba.'
)


class DescriptorInvalido(ValueError):
    """Lo que llego no tiene forma de descriptor."""


def limpiar(valor):
    """
    Devuelve el descriptor como lista de floats, o revienta.

    Llega de fuera, del navegador, asi que no se guarda nada sin mirarlo: un
    JSONField acepta cualquier cosa, y una lista de basura en la base se
    descubre meses despues, el dia que alguien no puede entrar.
    """
    if not isinstance(valor, (list, tuple)):
        raise DescriptorInvalido('El descriptor tiene que ser una lista.')
    if len(valor) != LARGO:
        raise DescriptorInvalido(
            f'El descriptor trae {len(valor)} numeros y deben ser {LARGO}.'
        )
    try:
        return [float(n) for n in valor]
    except (TypeError, ValueError) as error:
        raise DescriptorInvalido('El descriptor trae algo que no es numero.') from error


def distancia(uno, otro):
    """Que tan lejos estan dos caras. Cero es identica."""
    return sqrt(sum((a - b) ** 2 for a, b in zip(uno, otro)))


def buscar(gym, descriptor, umbral=UMBRAL):
    """
    A quien de este gimnasio se parece esta cara.

    Devuelve (cliente, distancia) o (None, la distancia mas cercana) cuando
    nadie queda dentro del umbral. La distancia se devuelve tambien al fallar
    porque es lo que dice si la camara vio mal o si de verdad era otra persona.

    Solo mira los rostros de ese gimnasio: los numeros de socio se repiten
    entre gimnasios y las caras tambien se podrian parecer, y nadie tiene por
    que entrar a un gimnasio donde no esta inscrito.
    """
    from clientes.models import Rostro

    descriptor = limpiar(descriptor)
    mejor, mejor_distancia = None, None

    guardados = (
        Rostro.objects.filter(gym=gym, activo=True, cliente__activo=True)
        .select_related('cliente')
    )
    for rostro in guardados:
        try:
            suyo = limpiar(rostro.descriptor)
        except DescriptorInvalido:
            # Una fila corrupta no puede dejar el kiosco inservible.
            continue
        d = distancia(descriptor, suyo)
        if mejor_distancia is None or d < mejor_distancia:
            mejor, mejor_distancia = rostro.cliente, d

    if mejor_distancia is not None and mejor_distancia <= umbral:
        return mejor, mejor_distancia
    return None, mejor_distancia
