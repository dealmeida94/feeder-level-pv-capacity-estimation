#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Modelo simplificado de PVWatts para geração de potência fotovoltaica.

Entrada:
    - irradiância solar [W/m²]
    - temperatura ambiente [°C]

Saída:
    - potência DC [kW]
    - potência AC [kW]
    - PVShape normalizado [pu]

O módulo foi desenvolvido para ser utilizado pelo construtor de cenários
do projeto BtM-PV-estimating.

Arquitetura:
    irradiância + temperatura
              ↓
        temperatura da célula
              ↓
          potência DC
              ↓
       perdas do inversor
              ↓
          potência AC
              ↓
       PVShape normalizado
"""

import numpy as np
import pandas as pd


# ============================================================================
# PARÂMETROS DO MODELO
# ============================================================================

# Coeficiente de temperatura da potência DC [1/°C].
# Valor típico utilizado para módulos de silício.
GAMMA_PDC = -0.004

# Elevação de temperatura da célula em relação à temperatura ambiente
# para irradiância de 1000 W/m² [°C].
DELTA_T_REF = 20.0

# Eficiência nominal do inversor.
EFICIENCIA_INVERSOR = 0.96


# ============================================================================
# TEMPERATURA DA CÉLULA
# ============================================================================

def calcula_temperatura_celula(
        irradiancia,
        temperatura_ambiente,
        delta_t_ref=DELTA_T_REF
    ):
    """
    Calcula uma temperatura aproximada da célula FV.

    Modelo:
        Tcell = Tamb + (G / 1000) * delta_t_ref

    Parâmetros
    ----------
    irradiancia : array-like
        Irradiância [W/m²].

    temperatura_ambiente : array-like
        Temperatura ambiente [°C].

    delta_t_ref : float
        Elevação de temperatura da célula em relação ao ambiente
        para G = 1000 W/m².

    Retorno
    -------
    numpy.ndarray
        Temperatura da célula [°C].
    """

    G = np.asarray(
        irradiancia,
        dtype=float
    )

    Tamb = np.asarray(
        temperatura_ambiente,
        dtype=float
    )

    if G.shape != Tamb.shape:
        raise ValueError(
            "Irradiância e temperatura ambiente devem possuir "
            "o mesmo tamanho."
        )

    # Irradiância negativa não possui significado físico.
    G = np.maximum(
        G,
        0.0
    )

    Tcell = (
        Tamb
        +
        (G / 1000.0) * delta_t_ref
    )

    return Tcell


# ============================================================================
# POTÊNCIA FOTOVOLTAICA
# ============================================================================

def calcula_potencia_dc(
        irradiancia,
        temperatura_celula,
        potencia_nominal,
        gamma_pdc=GAMMA_PDC
    ):
    """
    Calcula a potência DC do sistema FV.

    O modelo considera:
        Pdc = Pnom * (G / 1000) *
              [1 + gamma * (Tcell - 25)]

    A potência é limitada a zero.

    Parâmetros
    ----------
    irradiancia : array-like
        Irradiância [W/m²].

    temperatura_celula : array-like
        Temperatura da célula [°C].

    potencia_nominal : float
        Potência nominal DC [kW].

    gamma_pdc : float
        Coeficiente de temperatura [1/°C].

    Retorno
    -------
    numpy.ndarray
        Potência DC [kW].
    """

    G = np.asarray(
        irradiancia,
        dtype=float
    )

    Tcell = np.asarray(
        temperatura_celula,
        dtype=float
    )

    if G.shape != Tcell.shape:
        raise ValueError(
            "Irradiância e temperatura da célula devem possuir "
            "o mesmo tamanho."
        )

    if potencia_nominal < 0:
        raise ValueError(
            "A potência nominal não pode ser negativa."
        )

    G = np.maximum(
        G,
        0.0
    )

    potencia_dc = (
        potencia_nominal
        *
        (G / 1000.0)
        *
        (
            1.0
            +
            gamma_pdc * (Tcell - 25.0)
        )
    )

    # Não permite potência DC negativa.
    potencia_dc = np.maximum(
        potencia_dc,
        0.0
    )

    return potencia_dc


# ============================================================================
# POTÊNCIA AC / INVERSOR
# ============================================================================

def calcula_potencia_ac(
        potencia_dc,
        eficiencia_inversor=EFICIENCIA_INVERSOR
    ):
    """
    Aplica as perdas do inversor.

    P_ac = P_dc * eficiência_inversor
    """

    Pdc = np.asarray(
        potencia_dc,
        dtype=float
    )

    if not 0 < eficiencia_inversor <= 1:
        raise ValueError(
            "A eficiência do inversor deve estar entre 0 e 1."
        )

    potencia_ac = (
        Pdc
        *
        eficiencia_inversor
    )

    # Não permite potência AC negativa.
    potencia_ac = np.maximum(
        potencia_ac,
        0.0
    )

    return potencia_ac


# ============================================================================
# MODELO COMPLETO
# ============================================================================

def calcula_pvwatts(
        irradiancia,
        temperatura_ambiente,
        potencia_nominal,
        gamma_pdc=GAMMA_PDC,
        delta_t_ref=DELTA_T_REF,
        eficiencia_inversor=EFICIENCIA_INVERSOR
    ):
    """
    Executa o modelo completo:

        irradiância + temperatura ambiente
                    ↓
             temperatura célula
                    ↓
                potência DC
                    ↓
              perdas inversor
                    ↓
                potência AC

    Retorna um DataFrame.
    """

    G = np.asarray(
        irradiancia,
        dtype=float
    )

    Tamb = np.asarray(
        temperatura_ambiente,
        dtype=float
    )

    if G.shape != Tamb.shape:
        raise ValueError(
            "Irradiância e temperatura ambiente devem possuir "
            "o mesmo tamanho."
        )

    if np.isnan(G).any():
        raise ValueError(
            "A irradiância contém valores NaN."
        )

    if np.isnan(Tamb).any():
        raise ValueError(
            "A temperatura ambiente contém valores NaN."
        )

    Tcell = calcula_temperatura_celula(
        G,
        Tamb,
        delta_t_ref=delta_t_ref
    )

    Pdc = calcula_potencia_dc(
        G,
        Tcell,
        potencia_nominal,
        gamma_pdc=gamma_pdc
    )

    Pac = calcula_potencia_ac(
        Pdc,
        eficiencia_inversor=eficiencia_inversor
    )

    resultado = pd.DataFrame({
        "irradiancia_W_m2": G,
        "temperatura_ambiente_C": Tamb,
        "temperatura_celula_C": Tcell,
        "potencia_DC_kW": Pdc,
        "potencia_AC_kW": Pac
    })

    return resultado


# ============================================================================
# CURVA NORMALIZADA PARA PVShape
# ============================================================================

def gera_pvshape(
        irradiancia,
        temperatura_ambiente,
        gamma_pdc=GAMMA_PDC,
        delta_t_ref=DELTA_T_REF
    ):
    """
    Gera uma curva de geração normalizada para utilização
    como PVShape no OpenDSS.

    A potência nominal é fixada em 1 kW apenas para obter
    a curva normalizada.

    A saída representa a fração da potência nominal produzida
    em cada instante e é limitada entre 0 e 1 pu.
    """

    resultado = calcula_pvwatts(
        irradiancia=irradiancia,
        temperatura_ambiente=temperatura_ambiente,
        potencia_nominal=1.0,
        gamma_pdc=gamma_pdc,
        delta_t_ref=delta_t_ref
    )

    # O OpenDSS trabalha com a potência AC do PVSystem.
    pvshape = resultado[
        "potencia_AC_kW"
    ].to_numpy()

    # Garante a faixa física do PVShape.
    pvshape = np.clip(
        pvshape,
        0.0,
        1.0
    )

    return pvshape


# ============================================================================
# TESTE RÁPIDO
# ============================================================================

if __name__ == "__main__":

    irradiancia = np.array([
        0, 0, 100, 300, 500, 700, 900,
        1000, 900, 700, 500, 300, 100, 0
    ])

    temperatura = np.array([
        20, 19, 19, 20, 22, 25, 28,
        30, 31, 30, 28, 25, 22, 20
    ])

    resultado = calcula_pvwatts(
        irradiancia,
        temperatura,
        potencia_nominal=10.0
    )

    print("\nResultado do modelo PVWatts:")
    print(resultado.to_string(index=False))

    pvshape = gera_pvshape(
        irradiancia,
        temperatura
    )

    print(
        f"\nEficiência do inversor: "
        f"{EFICIENCIA_INVERSOR:.1%}"
    )

    print("\nPVShape:")
    print(pvshape)

    print(
        f"\nPVShape mínimo: {pvshape.min():.6f}"
    )

    print(
        f"PVShape máximo: {pvshape.max():.6f}"
    )
