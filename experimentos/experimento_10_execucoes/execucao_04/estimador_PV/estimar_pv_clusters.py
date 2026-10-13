#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import numpy as np
import pandas as pd
from itertools import combinations


def estimar_pv(
    df_cluster,
    potencia_real,
    k
):
    """
    Estima a potência FV instalada a partir das diferenças
    entre pares de dias de um cluster.

    Parameters
    ----------
    df_cluster : DataFrame
        Deve conter as colunas:
            dia
            hora
            P_kW
            Q_kvar
            irradiancia_W_m2

    potencia_real : float or None
        Potência FV real, utilizada apenas para calcular
        as métricas de erro.

    k : float
        Coeficiente de ajuste utilizado no modelo.

    Returns
    -------
    resultado : dict
        Contém:
            Pinst
            alpha
            cov_alpha
            variancia_Pinst
            desvio_padrao_Pinst
            sigma2
            RMSE
            MAE
            R2
            num_equacoes
            erro_percentual
            acerto
    """

    dias = np.sort(df_cluster["dia"].unique())

    lista_deltaP = []
    lista_deltaQ = []
    lista_deltaG = []

    # ==========================================================
    # Monta todas as equações
    # ==========================================================

    for dia1, dia2 in combinations(dias, 2):

        dados1 = (
            df_cluster[df_cluster["dia"] == dia1]
            .sort_values("hora")
        )

        dados2 = (
            df_cluster[df_cluster["dia"] == dia2]
            .sort_values("hora")
        )

        comum = pd.merge(
            dados1,
            dados2,
            on="hora",
            suffixes=("_1", "_2")
        )

        if comum.empty:
            continue

        deltaP = (
            comum["P_kW_2"].to_numpy()
            - comum["P_kW_1"].to_numpy()
        )

        deltaQ = (
            comum["Q_kvar_2"].to_numpy()
            - comum["Q_kvar_1"].to_numpy()
        )

        deltaG = (
            comum["irradiancia_W_m2_2"].to_numpy()
            - comum["irradiancia_W_m2_1"].to_numpy()
        )

        lista_deltaP.extend(deltaP)
        lista_deltaQ.extend(deltaQ)
        lista_deltaG.extend(deltaG)

    deltaP = np.asarray(lista_deltaP)
    deltaQ = np.asarray(lista_deltaQ)
    deltaG = np.asarray(lista_deltaG)

    if len(deltaP) == 0:
        raise ValueError("Nenhuma equação foi formada.")

    # ==========================================================
    # Matriz de regressão
    # ==========================================================

    A = np.column_stack(
        (
            deltaQ,
            -(k / 1000.0) * deltaG
        )
    )

    # ==========================================================
    # Regressão OLS
    # ==========================================================

    alpha, *_ = np.linalg.lstsq(
        A,
        deltaP,
        rcond=None
    )

    # Potência FV estimada
    Pinst = alpha[1]

    # ==========================================================
    # Resíduos
    # ==========================================================

    deltaP_est = A @ alpha

    erro = deltaP - deltaP_est

    SSE = np.sum(erro**2)

    n = len(deltaP)
    p = A.shape[1]

    # ==========================================================
    # Variância residual
    # ==========================================================

    graus_liberdade = n - p

    if graus_liberdade > 0:
        sigma2 = SSE / graus_liberdade
    else:
        sigma2 = np.nan

    # ==========================================================
    # Covariância dos parâmetros alpha
    #
    # Cov(alpha) = sigma² (AᵀA)^(-1)
    # ==========================================================

    posto = np.linalg.matrix_rank(A)

    if posto == p and graus_liberdade > 0:

        ATA = A.T @ A

        cov_alpha = (
            sigma2
            * np.linalg.inv(ATA)
        )

        variancia_Pinst = cov_alpha[1, 1]

        desvio_padrao_Pinst = np.sqrt(
            variancia_Pinst
        )

    else:

        cov_alpha = np.full(
            (p, p),
            np.nan
        )

        variancia_Pinst = np.nan
        desvio_padrao_Pinst = np.nan

    # ==========================================================
    # Métricas
    # ==========================================================

    rmse = np.sqrt(
        np.mean(erro**2)
    )

    mae = np.mean(
        np.abs(erro)
    )

    denominador_r2 = np.sum(
        (deltaP - np.mean(deltaP))**2
    )

    if denominador_r2 > 0:

        r2 = (
            1
            - SSE / denominador_r2
        )

    else:

        r2 = np.nan

    # ==========================================================
    # Resultado
    # ==========================================================

    resultado = {

        # Estimativa
        "Pinst": Pinst,

        # Parâmetros da regressão
        "alpha": alpha,

        # Covariância dos parâmetros
        "cov_alpha": cov_alpha,

        # Incerteza da estimativa de Pinst
        "variancia_Pinst": variancia_Pinst,
        "desvio_padrao_Pinst": desvio_padrao_Pinst,

        # Variância residual
        "sigma2": sigma2,

        # Métricas do ajuste
        "RMSE": rmse,
        "MAE": mae,
        "R2": r2,

        # Informações da regressão
        "num_equacoes": n,
        "graus_liberdade": graus_liberdade,
        "posto_A": posto,

    }

    # ==========================================================
    # Erro em relação à potência real
    # ==========================================================

    if potencia_real is not None:

        erro_percentual = (
            100
            * abs(Pinst - potencia_real)
            / potencia_real
        )

        resultado["erro_percentual"] = erro_percentual

        resultado["acerto"] = (
            100
            - erro_percentual
        )

    return resultado