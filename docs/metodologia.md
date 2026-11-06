# Metodología — Orquestador NBA Configurable

> **Versión preliminar.** Este documento lo mantiene el responsable del modelo (Juan Reina). La consola lo muestra
> tal cual en la página *Metodología*. Las decisiones de modelado marcadas con **TODO** están pendientes.

## 1. El problema

Para cada cliente $i$ hay que decidir qué campañas $p$ ofrecerle y por qué canal $c$, maximizando el valor esperado
sin violar ninguna regla del negocio y respetando los cupos de cada canal. Los conjuntos, valores, umbrales, cupos y
reglas salen de la configuración: la tabla de símbolos de abajo se genera a partir de ella en cada corrida.

## 2. Variables

$$
Z_i^{p,c} \in \{0,1\}\quad\text{(ofrecer } p \text{ a } i \text{ por } c\text{)}, \qquad
Z_i^{c} \in \{0,1\}\quad\text{(contactar a } i \text{ por } c\text{)}
$$

## 3. Objetivo

$$
\max \sum_{i}\sum_{p}\sum_{c} \Big( w_{\text{valor}}\, SP_i^{p}\, SC_i^{c}\, VN_p \;+\; w_{\text{jer}}\, N_p \;+\; B_i^{p,c} \Big)\, Z_i^{p,c}
$$

- $SP_i^p \cdot SC_i^c \cdot VN_p$ es la métrica oficial de valor esperado.
- $N_p$ es el nivel de jerarquía de la campaña (1 la primera, 0 la última) y $w_{\text{jer}}$ su peso
  (`objetivo.peso_jerarquia`). **TODO:** cómo se pondera la jerarquía frente al valor.
- $B_i^{p,c}$ suma las reglas blandas activas (bonificar / penalizar). No cuenta en la métrica oficial.

## 4. Restricciones

| Restricción | Forma |
|---|---|
| Activación del canal y productos por contacto (R14) | $\sum_p Z_i^{p,c} \le M_c\, Z_i^{c}$ |
| Canales por cliente (R13) y tope semanal (R15) | $\sum_c Z_i^{c} \le \min(\text{canales\_por\_cliente},\ \text{tope} - \text{contactos ya recibidos})$ |
| Cupo de cada canal (R16) | $\sum_i Z_i^{c} \le K_c$ |
| Elegibilidad (R01–R07), umbral de producto (R08) | $Z_i^{p,c} = 0$ si alguna regla excluye el par $(i,p)$ o $SP_i^p < U_p$ |
| Canal (R09–R11), canales permitidos (R12) | $Z_i^{p,c} = 0$ si el canal está bloqueado para $i$, $SC_i^c < U_c$ o $p$ no se permite por $c$ |
| Restricciones de negocio | $\sum_{(i,p,c) \in S} m_{i,p,c}\, Z_i^{p,c} \;\lessgtr\; L$ (cuotas lineales de `config_restricciones`) |

Las exclusiones no se escriben como millones de filas $Z \le 0$: esas variables simplemente no se crean (máscaras).
Es matemáticamente lo mismo y cada par eliminado conserva el ID de la regla que lo quitó, que es lo que muestra la
explicación de cada cliente.

## 5. Optimizadores

- **Línea base (codiciosa):** ordena a los clientes por el puntaje de su mejor campaña y asigna el mejor canal con
  cupo. Rápida y explicable; no ve el conjunto y agota primero los cupos escasos.
- **MILP (HiGHS):** resuelve el modelo completo y entrega los precios sombra de los cupos y de las cuotas.
  **TODO:** formulación final, tiempo límite (`optimizador.tiempo_max_s`) y brecha (`optimizador.gap`).
