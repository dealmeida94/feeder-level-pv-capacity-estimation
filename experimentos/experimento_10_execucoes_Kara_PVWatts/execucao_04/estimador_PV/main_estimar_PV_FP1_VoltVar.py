#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Realiza a estimação da potência PV instalada para os diferentes cenários
de penetração.

A lógica matemática do estimador é mantida integralmente.

A única alteração estrutural é que o processo é executado separadamente para:
    1. FP = 1
    2. Volt-VAr

Os resultados são salvos separadamente. A comparação entre os dois
experimentos será realizada por um script específico de comparação.
"""

import pandas as pd
import numpy as np
import time
from pathlib import Path
import sys

from localizar_clusters import localizar_clusters
from carregar_clusters import carregar_clusters
from estimar_pv_clusters import estimar_pv


# ============================================================================
# CONFIGURAÇÕES
#
# Existe um único configs.py na RAIZ do projeto.
# O estimador deve sempre importar esse arquivo, independentemente
# de onde o script esteja sendo executado.

ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT / "configs.py"

if not CONFIG_FILE.exists():
    raise FileNotFoundError(
        f"Arquivo configs.py não encontrado na raiz do projeto:\n{CONFIG_FILE}"
    )

sys.path.insert(0, str(ROOT))

import configs as cfg

# Verificação para evitar que um configs.py existente em outra pasta
# seja importado por engano.
if Path(cfg.__file__).resolve() != CONFIG_FILE.resolve():
    raise ImportError(
        "O configs.py importado não corresponde ao configs.py da raiz do projeto.\n"
        f"Esperado: {CONFIG_FILE.resolve()}\n"
        f"Importado: {Path(cfg.__file__).resolve()}"
    )


KS = [0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1]


# ============================================================================
# ETAPA 1 - POTÊNCIA REAL INSERIDA EM CADA CENÁRIO

def carregar_potencias_reais():

    caminho = Path(cfg.POTENCIAS_CENARIOS)

    if not caminho.exists():
        raise FileNotFoundError(
            f"Arquivo de potência real não encontrado:\n{caminho}"
        )

    df = pd.read_excel(caminho)

    return dict(
        zip(
            df["cenario"],
            df["potencia_PV_kW"]
        )
    )


# ============================================================================
# EXECUTA O ESTIMADOR PARA UMA CONDIÇÃO EXPERIMENTAL

def executar_estimacao(tipo, potencias_reais):

    if tipo not in ("FP1", "VV"):
        raise ValueError(
            "tipo deve ser 'FP1' ou 'VV'."
        )

    inicio = time.perf_counter()

    nome_tipo = (
        "FP = 1"
        if tipo == "FP1"
        else "Volt-VAr"
    )

    print()
    print("=" * 70)
    print(f"ESTIMAÇÃO DE POTÊNCIA PV - {nome_tipo}")
    print("=" * 70)

    # ------------------------------------------------------------------------
    # Etapa 2 - Localiza e carrega os clusters

    arquivos = localizar_clusters(tipo)

    if len(arquivos) == 0:
        raise RuntimeError(
            f"Nenhum cluster encontrado para {nome_tipo}."
        )

    dados_clusters = carregar_clusters(arquivos)

    # ------------------------------------------------------------------------
    # Etapa 3 - Executa o modelo de estimação

    resultados_gerais = []

    for k in KS:

        print("=" * 60)
        print(f"\nEstimativa com k = {k:.2f}")

        for cenario, clusters in dados_clusters.items():

            if cenario not in potencias_reais:
                raise KeyError(
                    f"Potência real do cenário {cenario}% "
                    "não encontrada em Potencias_Cenarios.xlsx."
                )

            potencia_real = potencias_reais[cenario]

            print(f"\nNível PV = {cenario}%")

            for numero_cluster, df_cluster in clusters.items():

                resultado = estimar_pv(
                    df_cluster=df_cluster,
                    potencia_real=potencia_real,
                    k=k
                )

                resultados_gerais.append(
                    {
                        "Tipo": tipo,
                        "k": k,
                        "Cenário": cenario,
                        "Cluster": numero_cluster,

                        "Potência Real (kW)": potencia_real,
                        "Potência estimada (kW)": resultado["Pinst"],

                        "Alpha 1": resultado["alpha"][0],
                        "Alpha 2": resultado["alpha"][1],

                        "Variância Pinst":
                            resultado["variancia_Pinst"],

                        "Desvio padrão Pinst":
                            resultado["desvio_padrao_Pinst"],

                        "Cov(alpha1, alpha1)":
                            resultado["cov_alpha"][0, 0],

                        "Cov(alpha1, alpha2)":
                            resultado["cov_alpha"][0, 1],

                        "Cov(alpha2, alpha1)":
                            resultado["cov_alpha"][1, 0],

                        "Cov(alpha2, alpha2)":
                            resultado["cov_alpha"][1, 1],

                        "Sigma²": resultado["sigma2"],

                        "Erro (%)":
                            resultado["erro_percentual"],

                        "Acerto (%)":
                            resultado["acerto"],

                        "RMSE": resultado["RMSE"],
                        "MAE": resultado["MAE"],
                        "R²": resultado["R2"],

                        "Equações":
                            resultado["num_equacoes"],

                        "Graus de liberdade":
                            resultado["graus_liberdade"],

                        "Posto A":
                            resultado["posto_A"],
                    }
                )

                print(
                    f"  Cluster {numero_cluster} | "
                    f"P = {resultado['Pinst']:.2f} kW | "
                    f"Erro = {resultado['erro_percentual']:.2f}% | "
                    f"Var = {resultado['variancia_Pinst']:.6f}"
                )

        print()
        print("=" * 60)

    # ------------------------------------------------------------------------
    # DataFrame com resultados individuais

    resultados = pd.DataFrame(
        resultados_gerais
    )

    # ------------------------------------------------------------------------
    # Etapa 4 - Combinação ótima das estimativas dos clusters
    #
    # Mantida exatamente a lógica original:
    #
    #       w_i = (1 / Var_i) / sum(1 / Var_j)
    #
    #       P_final = sum(w_i * P_i)

    resultados_finais = []

    for (k, cenario), grupo in resultados.groupby(
        ["k", "Cenário"]
    ):

        grupo = grupo.copy()

        variancias = grupo[
            "Variância Pinst"
        ].to_numpy()

        if (
            np.any(~np.isfinite(variancias))
            or np.any(variancias <= 0)
        ):

            raise ValueError(
                f"Variância inválida para o cenário "
                f"{cenario}% com k = {k}."
            )

        precisao = 1.0 / variancias

        pesos = precisao / np.sum(precisao)

        grupo["Peso"] = pesos

        potencia_estimada = np.sum(
            grupo["Peso"].to_numpy()
            *
            grupo[
                "Potência estimada (kW)"
            ].to_numpy()
        )

        potencia_real = grupo[
            "Potência Real (kW)"
        ].iloc[0]

        erro_percentual = (
            100
            *
            abs(
                potencia_estimada
                -
                potencia_real
            )
            /
            potencia_real
        )

        acerto = 100 - erro_percentual

        variancia_final = np.sum(
            pesos**2 * variancias
        )

        desvio_padrao_final = np.sqrt(
            variancia_final
        )

        resultados_finais.append(
            {
                "Tipo": tipo,
                "k": k,
                "Cenário": cenario,

                "Potência Real (kW)":
                    potencia_real,

                "Potência estimada final (kW)":
                    potencia_estimada,

                "Erro (%)":
                    erro_percentual,

                "Acerto (%)":
                    acerto,

                "Variância final":
                    variancia_final,

                "Desvio padrão final":
                    desvio_padrao_final,

                "Cluster 1":
                    grupo.loc[
                        grupo["Cluster"] == 1,
                        "Potência estimada (kW)"
                    ].iloc[0]
                    if 1 in grupo["Cluster"].values
                    else np.nan,

                "Peso C1":
                    grupo.loc[
                        grupo["Cluster"] == 1,
                        "Peso"
                    ].iloc[0]
                    if 1 in grupo["Cluster"].values
                    else np.nan,

                "Cluster 2":
                    grupo.loc[
                        grupo["Cluster"] == 2,
                        "Potência estimada (kW)"
                    ].iloc[0]
                    if 2 in grupo["Cluster"].values
                    else np.nan,

                "Peso C2":
                    grupo.loc[
                        grupo["Cluster"] == 2,
                        "Peso"
                    ].iloc[0]
                    if 2 in grupo["Cluster"].values
                    else np.nan,

                "Cluster 3":
                    grupo.loc[
                        grupo["Cluster"] == 3,
                        "Potência estimada (kW)"
                    ].iloc[0]
                    if 3 in grupo["Cluster"].values
                    else np.nan,

                "Peso C3":
                    grupo.loc[
                        grupo["Cluster"] == 3,
                        "Peso"
                    ].iloc[0]
                    if 3 in grupo["Cluster"].values
                    else np.nan,

                "Cluster 4":
                    grupo.loc[
                        grupo["Cluster"] == 4,
                        "Potência estimada (kW)"
                    ].iloc[0]
                    if 4 in grupo["Cluster"].values
                    else np.nan,

                "Peso C4":
                    grupo.loc[
                        grupo["Cluster"] == 4,
                        "Peso"
                    ].iloc[0]
                    if 4 in grupo["Cluster"].values
                    else np.nan,
            }
        )

        # --------------------------------------------------------------------
        # Exibe resultado final

        print(
            f"\n  >>> RESULTADO FINAL - "
            f"Cenário {cenario}% - {nome_tipo}"
        )

        print(
            f"      Potência real      = "
            f"{potencia_real:.2f} kW"
        )

        print(
            f"      Potência estimada  = "
            f"{potencia_estimada:.2f} kW"
        )

        print(
            f"      Erro               = "
            f"{erro_percentual:.2f}%"
        )

        print(
            f"      Acerto             = "
            f"{acerto:.2f}%"
        )

        print(
            f"      Desvio padrão      = "
            f"{desvio_padrao_final:.4f} kW"
        )

        print("      Pesos:")

        for _, linha in grupo.sort_values(
            "Cluster"
        ).iterrows():

            print(
                f"        C{int(linha['Cluster'])}: "
                f"{linha['Peso']:.4f}"
            )

    # ------------------------------------------------------------------------
    # DataFrame dos resultados finais

    finais = pd.DataFrame(
        resultados_finais
    )

    # ------------------------------------------------------------------------
    # Etapa 5 - Salva os resultados

    pasta_saida = Path(
        cfg.OUT_ESTIMACAO
    )

    pasta_saida.mkdir(
        parents=True,
        exist_ok=True
    )

    arquivo_clusters = (
        pasta_saida
        /
        f"Resultados_da_estimacao_por_clusters_{tipo}.xlsx"
    )

    arquivo_finais = (
        pasta_saida
        /
        f"Resultados_finais_por_cenario_{tipo}.xlsx"
    )

    resultados.to_excel(
        arquivo_clusters,
        index=False
    )

    finais.to_excel(
        arquivo_finais,
        index=False
    )

    print()
    print("Arquivos salvos:")

    print(
        f"  - {arquivo_clusters}"
    )

    print(
        f"  - {arquivo_finais}"
    )

    fim = time.perf_counter()

    tempo_total = fim - inicio

    minutos = int(
        (tempo_total % 3600) // 60
    )

    segundos = tempo_total % 60

    print(
        f"\nTempo de execução {nome_tipo}: "
        f"{minutos:02d}:{segundos:05.2f}"
    )

    return resultados, finais


# ============================================================================
# MAIN

def main():

    inicio = time.perf_counter()

    potencias_reais = carregar_potencias_reais()

    # ------------------------------------------------------------------------
    # Executa exatamente o mesmo estimador para as duas condições.
    resultados_fp1, finais_fp1 = executar_estimacao(
        "FP1",
        potencias_reais
    )

    resultados_vv, finais_vv = executar_estimacao(
        "VV",
        potencias_reais
    )

    fim = time.perf_counter()

    tempo_total = fim - inicio

    minutos = int(
        (tempo_total % 3600) // 60
    )

    segundos = tempo_total % 60

    print()
    print("=" * 70)
    print("ESTIMAÇÕES CONCLUÍDAS")
    print("=" * 70)

    print(
        f"Tempo total: "
        f"{minutos:02d}:{segundos:05.2f}"
    )

    return {
        "FP1": {
            "clusters": resultados_fp1,
            "finais": finais_fp1,
        },
        "VV": {
            "clusters": resultados_vv,
            "finais": finais_vv,
        },
    }


if __name__ == "__main__":
    resultado = main()
