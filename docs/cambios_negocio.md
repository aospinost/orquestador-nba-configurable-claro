# Cambios de negocio desde la consola (sin código)

Cómo resolver cada tipo de cambio del reto. Todo cambio queda **en borrador** (aviso rojo "Tienes N cambios sin
aplicar") hasta pulsar **Aplicar y re-optimizar** al final de la página o en **Ver impacto**. Al aplicar se valida,
se guarda una copia con fecha en `config/history/` y se vuelve a optimizar. **Descartar cambios** vuelve a la última
configuración aplicada; **Configuración → Restaurar configuración inicial** (barra lateral) carga la de los
organizadores.

Arranque: `.venv/Scripts/streamlit run app/Inicio.py` → http://localhost:8501

| # | Tipo de cambio | Clics |
|---|---|---|
| 1 | **Campañas** — lanzar una campaña nueva | *Campañas* → **Nueva campaña** → código de producto, nombre, objetivo (o uno nuevo), columna de score, valor, canales, vigencia → **Crear campaña** |
| 1 | Pausar sin borrar | *Campañas* → apagar el interruptor **Activa y vigente** de la tarjeta (queda gris, "Pausada") |
| 1 | Cambiar sus canales / valor / vigencia | *Campañas* → **Edición en tabla** → editar la celda (Canales permitidos, Valor, Desde/Hasta) |
| 2 | **Reglas** — crear una regla sobre cualquier columna | *Reglas* → pestaña **Reglas** → Acción · A (campañas / productos / objetivos / canales / todas) · Cuáles · Cuando [columna] [operador] [valor] → ver "Esta regla afecta a N clientes" → **Agregar regla** |
| 2 | Restringir una campaña a ciertas calificaciones | igual que arriba con *A = las campañas… → C-XXX*, *Cuando = calificacion_riesgo*, *no está en*, valores permitidos |
| 2 | Aplicar una regla a un grupo de campañas | *A = los objetivos…* (o *los productos…*) y elegir el grupo |
| 2 | Apagar / editar / duplicar / eliminar una regla | *Reglas* → interruptor de la fila · lápiz · copiar · papelera |
| 2 | Lógica compuesta (Y/O, por producto) | *Reglas* → pestaña **Constantes derivadas** → símbolo, condiciones Y/O → **Agregar constante**; luego una regla con *Cuando = [constante]* |
| 3 | **Umbrales** — score mínimo de producto o canal | *Prioridad y canales* → paso 3 → mover **Score mínimo de producto / de canal** (el histograma muestra cuántos clientes quedan por debajo). Umbral propio de una campaña: *Campañas* → tabla → **Umbral propio**; de un canal: tabla de canales → **Umbral propio** |
| 4 | **Prioridad** — cambiar la jerarquía | *Prioridad y canales* → paso 1 → flechas ↑ ↓ |
| 4 | Más o menos peso al modelo frente al valor | *Prioridad y canales* → paso 2 → mover un peso; los otros se ajustan para sumar 1. Modo **Ponderado** o **Jerarquía estricta** en el paso 1 |
| 5 | **Canales y cupos** — cambiar el cupo o productos por contacto | *Prioridad y canales* → paso 4 → tabla → celdas **Cupo por corrida** / **Productos por contacto** |
| 5 | Agregar un canal nuevo | *Prioridad y canales* → paso 4 → **Agregar canal** → ID, nombre, columna de score, cupo, productos, autorización, campañas → **Agregar canal** |
| 6 | **Política de contacto** — tope semanal | *Política de contacto* → paso 1 → **Máximo de contactos por semana** (contador de clientes afectados) |
| 6 | Tope de llamadas de asesor | *Política de contacto* → paso 3 → **Tope** de la regla del canal (p. ej. R11); también **Canales por cliente** en el paso 2 |
| 7 | **Datos** — usar una columna nueva | *Datos* → **Cargar otra base (CSV)** → aparece "Columnas nuevas detectadas" → la columna ya está en *Reglas*, *Constantes* y en las listas de columnas de score |

Las restricciones de negocio (cuotas: "como mínimo 5.000 contactos de una campaña") se crean en *Reglas* → pestaña
**Restricciones de negocio**; las aplica el optimizador MILP (fase 5) y la línea base solo reporta si se cumplen.
