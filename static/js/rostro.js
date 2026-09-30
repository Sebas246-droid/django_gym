/*
  Reconocimiento facial en el navegador.

  Lo usan dos pantallas: la de enrolar, en la ficha del socio, y el kiosco. Las
  dos hacen lo mismo — encender la camara y sacar el descriptor — y lo unico
  que viaja al servidor son esos 128 numeros. La foto no sale de aqui.

  El modelo pesa unos 7 MB y se descarga una sola vez: la tablet de la entrada
  lo deja en cache y a partir de ahi arranca solo.
*/
window.Rostro = (function () {
  let cargado = null;

  /*
    Hay que elegir con que motor corre TensorFlow antes de cargar nada, o falla
    con un "backend 'wasm' has not yet been initialized": por omision prefiere
    wasm, que necesita unos binarios aparte que no traemos. webgl usa la tarjeta
    de video y va bien hasta en una tablet barata; si no hay, cpu funciona
    igual, solo que mas lento.
  */
  async function motor() {
    for (const cual of ['webgl', 'cpu']) {
      try {
        await faceapi.tf.setBackend(cual);
        await faceapi.tf.ready();
        return cual;
      } catch (error) { /* se prueba el siguiente */ }
    }
    throw new Error('Este navegador no puede correr el reconocimiento.');
  }

  /* Los tres modelos: uno encuentra la cara, otro le pone los puntos y el
     tercero la describe. Se cargan una vez y se reusan. */
  function cargar(carpeta) {
    if (!cargado) {
      cargado = motor().then(function () {
        return Promise.all([
          faceapi.nets.tinyFaceDetector.loadFromUri(carpeta),
          faceapi.nets.faceLandmark68Net.loadFromUri(carpeta),
          faceapi.nets.faceRecognitionNet.loadFromUri(carpeta),
        ]);
      }).catch(function (error) {
        // Si fallo la descarga hay que olvidarla, o la promesa rechazada se
        // queda guardada y todos los intentos siguientes fallan igual sin
        // volver a intentarlo: el kiosco quedaria muerto hasta recargarlo, que
        // es justo lo que nadie va a hacer en la entrada de un gimnasio.
        cargado = null;
        throw error;
      });
    }
    return cargado;
  }

  async function encender(video) {
    // La camara solo se puede pedir en https o en localhost. En el kiosco de
    // un gimnasio eso siempre se cumple; decirlo claro ahorra media hora de
    // buscar por que "no pasa nada al tocar el boton".
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error('Este navegador no deja usar la camara.');
    }
    /*
      La camara de enfrente, en serio. 'user' a secas es una preferencia que el
      telefono puede ignorar —y la ignora: en un celular agarraba la trasera y
      el socio veia la pared—. Con 'exact' se exige, pero entonces falla donde
      no hay camara frontal, asi que se va aflojando la peticion hasta que
      alguna funcione.
    */
    const intentos = [
      { video: { facingMode: { exact: 'user' }, width: 640, height: 480 } },
      { video: { facingMode: 'user', width: 640, height: 480 } },
      { video: true },
    ];
    let senal = null;
    let ultimo = null;
    for (const peticion of intentos) {
      try {
        senal = await navigator.mediaDevices.getUserMedia(peticion);
        break;
      } catch (error) {
        ultimo = error;
      }
    }
    if (!senal) { throw ultimo || new Error('No hay camara disponible.'); }

    video.srcObject = senal;

    /*
      Esperar a que haya imagen, pero con tope. Una camara que acepta el
      permiso y despues no entrega nada dejaria el kiosco pensando para
      siempre, y con el a quien quiere entrar: mejor fallar y mandarlo al
      teclado.
    */
    try {
      await new Promise(function (listo, falla) {
        if (video.readyState >= 2) { listo(); return; }
        video.addEventListener('loadedmetadata', listo, { once: true });
        setTimeout(function () {
          falla(new Error('La camara no entrego imagen.'));
        }, 8000);
      });
    } catch (error) {
      // Si se rinde aqui hay que soltar la camara a mano: el permiso ya se
      // dio y la luz del aparato se quedaria encendida para siempre.
      apagar(video);
      throw error;
    }

    // El play puede quedarse colgado segun la politica del navegador. No se
    // espera indefinidamente: con los metadatos ya hay cuadro que leer.
    await Promise.race([
      video.play().catch(function () {}),
      new Promise(function (listo) { setTimeout(listo, 1500); }),
    ]);
    return senal;
  }

  function apagar(video) {
    const senal = video && video.srcObject;
    if (senal) {
      senal.getTracks().forEach(function (pista) { pista.stop(); });
      video.srcObject = null;
    }
  }

  /* Devuelve los 128 numeros de la cara que se vea, o null si no hay ninguna
     o si hay mas de una: con dos personas frente a la camara no se sabe a
     cual se le esta abriendo la puerta. */
  async function describir(video) {
    const caras = await faceapi
      .detectAllFaces(video, new faceapi.TinyFaceDetectorOptions())
      .withFaceLandmarks()
      .withFaceDescriptors();

    if (caras.length !== 1) { return null; }
    return Array.from(caras[0].descriptor);
  }

  /* Varias tomas seguidas, con una pausa entre ellas para que la persona se
     mueva un poco: tres angulos reconocen mejor que tres veces la misma foto. */
  async function tomas(video, cuantas, avisar) {
    const sacadas = [];
    for (let i = 0; i < cuantas; i += 1) {
      if (avisar) { avisar(i + 1, cuantas); }
      await new Promise(function (listo) { setTimeout(listo, 900); });
      const descriptor = await describir(video);
      if (descriptor) { sacadas.push(descriptor); }
    }
    return sacadas;
  }

  return { cargar, encender, apagar, describir, tomas };
})();
