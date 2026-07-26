/*
 * Desplegable con boton para dar de alta lo que falte, sin salir del formulario
 * ni perder lo ya capturado.
 *
 * Lo capturado en el modal NO se guarda al momento: viaja en campos ocultos y
 * el servidor lo crea al guardar el formulario. Asi no quedan registros sueltos
 * si el alta falla.
 *
 * Marcado esperado:
 *
 *   <div data-selector-modal data-nuevo="__nuevo__" [data-reusar]>
 *     <select id="...">...</select>
 *     <button type="button" data-abrir>Nuevo</button>
 *     <dialog data-modal>
 *       <input data-destino="id_campo_oculto" data-etiqueta data-obligatorio>
 *       <p data-aviso hidden>...</p>
 *       <button type="button" data-cancelar>Cancelar</button>
 *       <button type="button" data-guardar>Agregar</button>
 *     </dialog>
 *   </div>
 *
 * data-etiqueta   campo cuyo valor da nombre a la opcion nueva.
 * data-obligatorio no se puede dejar vacio.
 * data-destino    id del input oculto que lleva el valor al servidor.
 * data-reusar     si el nombre ya esta en la lista, elige ese en vez de
 *                 duplicarlo. Sirve para catalogos; no para personas, donde
 *                 dos registros pueden llamarse igual.
 */
(function () {
  document.querySelectorAll('[data-selector-modal]').forEach(function (raiz) {
    var lista = raiz.querySelector('select');
    var modal = raiz.querySelector('[data-modal]');
    var aviso = modal.querySelector('[data-aviso]');
    var campos = Array.prototype.slice.call(modal.querySelectorAll('[data-destino]'));
    var etiqueta = modal.querySelector('[data-etiqueta]');
    var NUEVO = raiz.dataset.nuevo;
    var reusar = raiz.hasAttribute('data-reusar');

    function oculto(campo) {
      return document.getElementById(campo.dataset.destino);
    }

    function limpiarOcultos() {
      campos.forEach(function (campo) { oculto(campo).value = ''; });
    }

    raiz.querySelector('[data-abrir]').addEventListener('click', function () {
      if (aviso) { aviso.hidden = true; }
      // Reabrir muestra lo que ya se habia capturado, para poder corregirlo.
      campos.forEach(function (campo) { campo.value = oculto(campo).value || ''; });
      modal.showModal();
      (etiqueta || campos[0]).focus();
    });

    raiz.querySelector('[data-cancelar]').addEventListener('click', function () {
      modal.close();
    });

    raiz.querySelector('[data-guardar]').addEventListener('click', function () {
      var faltante = campos.find(function (campo) {
        return campo.hasAttribute('data-obligatorio') && !campo.value.trim();
      });
      if (faltante) {
        if (aviso) { aviso.hidden = false; }
        faltante.focus();
        return;
      }

      var nombre = etiqueta.value.trim();
      var repetida = reusar && Array.prototype.find.call(lista.options, function (o) {
        return o.value && o.value !== NUEVO &&
               o.text.toLowerCase() === nombre.toLowerCase();
      });

      if (repetida) {
        lista.value = repetida.value;
        limpiarOcultos();
      } else {
        campos.forEach(function (campo) { oculto(campo).value = campo.value.trim(); });
        var opcion = Array.prototype.find.call(lista.options, function (o) {
          return o.value === NUEVO;
        });
        if (!opcion) {
          opcion = new Option(nombre, NUEVO);
          lista.add(opcion);
        }
        opcion.text = nombre;
        lista.value = NUEVO;
      }
      modal.close();
    });

    // Al elegir a mano otra opcion, lo capturado en el modal deja de valer.
    lista.addEventListener('change', function () {
      if (lista.value !== NUEVO) { limpiarOcultos(); }
    });

    campos.forEach(function (campo) {
      campo.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && campo.tagName !== 'TEXTAREA') {
          e.preventDefault();
          raiz.querySelector('[data-guardar]').click();
        }
      });
    });
  });
})();
