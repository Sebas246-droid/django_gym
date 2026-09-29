/*
  Botones de copiar al portapapeles.

  Cualquier boton con data-copiar="#donde" copia el texto de ese elemento y lo
  dice en el propio boton: sin aviso, uno no sabe si funciono y acaba copiando
  a mano por las dudas.

  Si el navegador no da permiso al portapapeles (pasa fuera de https), deja el
  texto seleccionado para copiarlo a mano en vez de fallar en silencio.
*/
document.addEventListener('click', async function (evento) {
  const boton = evento.target.closest('[data-copiar]');
  if (!boton) { return; }

  const origen = document.querySelector(boton.dataset.copiar);
  if (!origen) { return; }

  const texto = (origen.value !== undefined ? origen.value : origen.textContent).trim();
  const decia = boton.textContent;

  try {
    await navigator.clipboard.writeText(texto);
    boton.textContent = 'Copiado';
  } catch (error) {
    if (origen.select) { origen.select(); }
    boton.textContent = 'Copialo tu';
  }

  setTimeout(function () { boton.textContent = decia; }, 1600);
});
