"""
Que responde el bot a cada mensaje.

Son condicionales y menus, no un modelo de lenguaje: lo que el socio consulta
son sus propios datos y aqui una respuesta inventada seria peor que ninguna.
El menu ademas evita que tenga que adivinar como preguntar.
"""

from decimal import Decimal, InvalidOperation

from django.utils import timezone

from bot.models import (
    ALFABETO_CODIGO,
    ClienteTelegram,
    CodigoVinculacion,
    MedidaCorporal,
)
from clientes.models import NIVELES_ACTIVIDAD
from entrenamiento.models import Entrenamiento

# --- Menu -----------------------------------------------------------------

MEMBRESIA = 'Mi membresia'
ASISTENCIAS = 'Mis asistencias'
ENTRENAMIENTOS = 'Entrenamientos'
CALORIAS = 'Calorias'
AYUDA = 'Ayuda'

MENU = [[MEMBRESIA, ASISTENCIAS], [ENTRENAMIENTOS, CALORIAS], [AYUDA]]

CANCELAR = 'Cancelar'
MENU_CANCELAR = [[CANCELAR]]

# --- Calculadora ----------------------------------------------------------

#: Cuanto multiplica cada nivel al gasto en reposo.
FACTORES = {
    'sedentario': Decimal('1.2'),
    'ligero': Decimal('1.375'),
    'moderado': Decimal('1.55'),
    'intenso': Decimal('1.725'),
}
#: El texto del boton lleva al valor que se guarda en la ficha.
ACTIVIDAD_POR_TEXTO = {texto: valor for valor, texto in NIVELES_ACTIVIDAD}

MENU_ACTIVIDAD = [[texto] for texto in ACTIVIDAD_POR_TEXTO] + [[CANCELAR]]
MENU_SEXO = [['Hombre', 'Mujer'], [CANCELAR]]

PASO_PESO = 'peso'
PASO_ESTATURA = 'estatura'
PASO_EDAD = 'edad'
PASO_SEXO = 'sexo'
PASO_ACTIVIDAD = 'actividad'


class Respuesta:
    """Lo que el bot contesta: un texto y, si toca, un menu de botones."""

    def __init__(self, texto, botones=MENU):
        self.texto = texto
        self.botones = botones


# --- Punto de entrada ------------------------------------------------------


def responder(gym, chat_id, texto, nombre_telegram=''):
    """Traduce un mensaje recibido en la respuesta que hay que mandar."""
    texto = (texto or '').strip()
    enlace = (
        ClienteTelegram.objects.select_related('cliente')
        .filter(chat_id=chat_id, cliente__gym=gym, activo=True)
        .first()
    )

    if enlace is None:
        return _vincular(gym, chat_id, texto, nombre_telegram)

    if texto.lower() in ('/salir', '/stop'):
        return _desvincular(enlace)

    # Una conversacion a medias manda sobre el menu, salvo que la cancelen.
    if enlace.paso and texto != CANCELAR:
        return _seguir_calculadora(enlace, texto)
    if texto == CANCELAR:
        enlace.limpiar_paso()
        return Respuesta('Listo, lo dejamos ahi.')

    return _del_menu(enlace, texto)


# --- Vinculacion -----------------------------------------------------------


def _parece_codigo(texto):
    """
    Distingue un intento de codigo de un saludo. Sin esto, quien escribe 'Hola'
    recibe 'ese codigo no sirve', que no le dice nada de lo que tiene que hacer.
    """
    limpio = texto.upper().strip()
    return len(limpio) == 6 and all(c in ALFABETO_CODIGO for c in limpio)


def _vincular(gym, chat_id, texto, nombre_telegram):
    if not _parece_codigo(texto):
        return Respuesta(
            'Hola. Para ver tus datos primero hay que vincular este chat con tu '
            'cuenta.\n\nPidele a recepcion tu <b>codigo de acceso</b> y escribelo '
            'aqui. Dura 15 minutos.',
            botones=None,
        )

    codigo = (
        CodigoVinculacion.objects.select_related('cliente')
        .filter(codigo=texto.upper().strip(), cliente__gym=gym)
        .first()
    )
    if codigo is None or not codigo.vigente:
        return Respuesta(
            'Ese codigo no sirve o ya vencio. Pide uno nuevo en recepcion.',
            botones=None,
        )

    ClienteTelegram.objects.update_or_create(
        cliente=codigo.cliente,
        defaults={
            'chat_id': chat_id,
            'nombre_telegram': nombre_telegram[:150],
            'activo': True,
            'paso': '',
            'datos': {},
        },
    )
    codigo.usado_en = timezone.now()
    codigo.save(update_fields=['usado_en', 'updated_at'])

    return Respuesta(
        f'Listo, {codigo.cliente.nombre}. Ya puedes consultar tus datos desde '
        'aqui.\n\nUsa los botones de abajo.'
    )


def _desvincular(enlace):
    enlace.activo = False
    enlace.paso = ''
    enlace.datos = {}
    enlace.save(update_fields=['activo', 'paso', 'datos', 'updated_at'])
    return Respuesta(
        'Desvinculado. Ya no recibiras mensajes ni podras consultar tus datos '
        'desde aqui. Si cambias de idea, pide otro codigo en recepcion.',
        botones=None,
    )


# --- Menu ------------------------------------------------------------------


def _del_menu(enlace, texto):
    opciones = {
        MEMBRESIA: _membresia,
        ASISTENCIAS: _asistencias,
        ENTRENAMIENTOS: _entrenamientos,
        CALORIAS: _empezar_calculadora,
        AYUDA: _ayuda,
    }
    accion = opciones.get(texto)
    if accion is None:
        return Respuesta('Elige una opcion de los botones de abajo.')
    return accion(enlace)


def _ayuda(enlace):
    return Respuesta(
        'Esto es lo que puedo darte:\n\n'
        f'<b>{MEMBRESIA}</b> - hasta cuando esta vigente.\n'
        f'<b>{ASISTENCIAS}</b> - tus ultimas visitas.\n'
        f'<b>{ENTRENAMIENTOS}</b> - las rutinas del gimnasio.\n'
        f'<b>{CALORIAS}</b> - cuantas necesitas al dia.\n\n'
        'Escribe /salir para desvincular este chat.'
    )


def _membresia(enlace):
    cliente = enlace.cliente
    vigente = cliente.membresia_vigente
    if vigente is None:
        ultima = cliente.ultima_membresia
        if ultima is None:
            return Respuesta('No tienes ninguna membresia registrada todavia.')
        return Respuesta(
            f'Tu membresia <b>{ultima.membresia.nombre}</b> vencio el '
            f'{ultima.fin.strftime("%d/%m/%Y")}.\n\nPasa a recepcion para renovarla.'
        )

    dias = cliente.dias_restantes
    cierre = 'Vence hoy.' if dias == 0 else f'Te quedan <b>{dias}</b> dias.'
    return Respuesta(
        f'Tu membresia <b>{vigente.membresia.nombre}</b> esta vigente hasta el '
        f'{vigente.fin.strftime("%d/%m/%Y")}.\n\n{cierre}'
    )


def _asistencias(enlace):
    visitas = enlace.cliente.asistencias.order_by('-fecha_hora')[:5]
    if not visitas:
        return Respuesta('Todavia no tienes visitas registradas.')

    lineas = '\n'.join(
        f'- {timezone.localtime(v.fecha_hora).strftime("%d/%m/%Y a las %H:%M")}'
        for v in visitas
    )
    return Respuesta(f'Tus ultimas visitas:\n\n{lineas}')


def _entrenamientos(enlace):
    rutinas = Entrenamiento.objects.filter(gym=enlace.cliente.gym, activo=True)[:10]
    if not rutinas:
        return Respuesta('El gimnasio todavia no publica entrenamientos.')

    partes = []
    for rutina in rutinas:
        bloque = f'<b>{rutina.nombre}</b>'
        if rutina.descripcion:
            bloque += f'\n{rutina.descripcion}'
        if rutina.video:
            bloque += f'\nVideo: {rutina.video}'
        partes.append(bloque)
    return Respuesta('Entrenamientos del gimnasio:\n\n' + '\n\n'.join(partes))


# --- Calculadora de calorias -----------------------------------------------


def _preguntas_pendientes(cliente):
    """
    Solo se pregunta lo que no esta en la ficha. Con el socio bien capturado
    queda una sola pregunta: el peso, que es lo unico que cambia seguido.
    """
    pasos = [PASO_PESO]
    if cliente.estatura_cm is None:
        pasos.append(PASO_ESTATURA)
    if cliente.fecha_nacimiento is None:
        pasos.append(PASO_EDAD)
    if cliente.sexo not in ('M', 'F'):
        pasos.append(PASO_SEXO)
    if not cliente.nivel_actividad:
        pasos.append(PASO_ACTIVIDAD)
    return pasos


PREGUNTAS = {
    PASO_PESO: ('Cuanto pesas en kilos? Por ejemplo 78.5', MENU_CANCELAR),
    PASO_ESTATURA: ('Cuanto mides en centimetros? Por ejemplo 175', MENU_CANCELAR),
    PASO_EDAD: ('Cuantos anos tienes?', MENU_CANCELAR),
    PASO_SEXO: ('Para la formula, eres hombre o mujer?', MENU_SEXO),
    PASO_ACTIVIDAD: ('Cuantos dias por semana entrenas?', MENU_ACTIVIDAD),
}


def _empezar_calculadora(enlace):
    pendientes = _preguntas_pendientes(enlace.cliente)
    enlace.paso = pendientes[0]
    enlace.datos = {'pendientes': pendientes[1:]}
    enlace.save(update_fields=['paso', 'datos', 'updated_at'])
    pregunta, botones = PREGUNTAS[enlace.paso]
    return Respuesta(pregunta, botones=botones)


def _seguir_calculadora(enlace, texto):
    valor, error = _leer(enlace.paso, texto)
    if error:
        pregunta, botones = PREGUNTAS[enlace.paso]
        return Respuesta(f'{error}\n\n{pregunta}', botones=botones)

    datos = dict(enlace.datos)
    datos[enlace.paso] = valor
    pendientes = datos.get('pendientes', [])

    if pendientes:
        enlace.paso = pendientes[0]
        datos['pendientes'] = pendientes[1:]
        enlace.datos = datos
        enlace.save(update_fields=['paso', 'datos', 'updated_at'])
        pregunta, botones = PREGUNTAS[enlace.paso]
        return Respuesta(pregunta, botones=botones)

    enlace.limpiar_paso()
    return _resultado(enlace.cliente, datos)


def _leer(paso, texto):
    """Devuelve (valor, error). Solo uno de los dos viene lleno."""
    if paso == PASO_SEXO:
        elegido = texto.strip().lower()
        if elegido.startswith('h'):
            return 'M', None
        if elegido.startswith('m'):
            return 'F', None
        return None, 'No entendi.'

    if paso == PASO_ACTIVIDAD:
        if texto in ACTIVIDAD_POR_TEXTO:
            return ACTIVIDAD_POR_TEXTO[texto], None
        return None, 'Elige una de las opciones.'

    try:
        numero = Decimal(texto.replace(',', '.').strip())
    except (InvalidOperation, AttributeError):
        return None, 'Necesito un numero.'

    limites = {
        PASO_PESO: (Decimal('25'), Decimal('300'), 'El peso'),
        PASO_ESTATURA: (Decimal('100'), Decimal('250'), 'La estatura'),
        PASO_EDAD: (Decimal('10'), Decimal('110'), 'La edad'),
    }
    minimo, maximo, etiqueta = limites[paso]
    if not minimo <= numero <= maximo:
        return None, f'{etiqueta} tiene que estar entre {minimo:.0f} y {maximo:.0f}.'
    return str(numero), None


def _edad(cliente, datos):
    if PASO_EDAD in datos:
        return int(Decimal(datos[PASO_EDAD]))
    hoy = timezone.localdate()
    nacimiento = cliente.fecha_nacimiento
    return (
        hoy.year
        - nacimiento.year
        - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))
    )


def _resultado(cliente, datos):
    peso = Decimal(datos[PASO_PESO])
    edad = _edad(cliente, datos)
    estatura = (
        Decimal(datos[PASO_ESTATURA])
        if PASO_ESTATURA in datos
        else Decimal(cliente.estatura_cm)
    )
    sexo = datos.get(PASO_SEXO) or cliente.sexo
    actividad = datos.get(PASO_ACTIVIDAD) or cliente.nivel_actividad

    # Lo que el socio contesto se queda en su ficha: la proxima vez el bot solo
    # tiene que preguntarle el peso.
    _guardar_en_la_ficha(cliente, datos, estatura, sexo, actividad)
    MedidaCorporal.objects.create(cliente=cliente, peso_kg=peso)

    # Mifflin-St Jeor, la formula que mejor estima el gasto en reposo.
    basal = Decimal('10') * peso + Decimal('6.25') * estatura - Decimal('5') * edad
    basal += Decimal('5') if sexo == 'M' else Decimal('-161')
    mantenimiento = basal * FACTORES[actividad]
    texto_actividad = dict(NIVELES_ACTIVIDAD)[actividad].lower()

    return Respuesta(
        f'Con {peso} kg, {estatura:.0f} cm y {edad} anos, entrenando '
        f'{texto_actividad}:\n\n'
        f'En reposo tu cuerpo gasta <b>{basal:.0f}</b> calorias al dia.\n\n'
        f'Para <b>mantenerte</b>: {mantenimiento:.0f} al dia.\n'
        f'Para <b>bajar</b>: {mantenimiento - 500:.0f} al dia.\n'
        f'Para <b>subir</b>: {mantenimiento + 500:.0f} al dia.\n\n'
        'Es una estimacion, no una indicacion nutricional: para un plan de '
        'verdad consulta a un profesional.'
    )


def _guardar_en_la_ficha(cliente, datos, estatura, sexo, actividad):
    campos = []
    if PASO_ESTATURA in datos:
        cliente.estatura_cm = int(estatura)
        campos.append('estatura_cm')
    if PASO_SEXO in datos:
        cliente.sexo = sexo
        campos.append('sexo')
    if PASO_ACTIVIDAD in datos:
        cliente.nivel_actividad = actividad
        campos.append('nivel_actividad')
    if campos:
        cliente.save(update_fields=campos + ['updated_at'])
