"""
Realiza a estimação da potência PV instalada para os diferentes cenários
de penetração.

Etapas do processo de estimação:
    1. Carrega as potências reais inseridas em cada cenário;
    2. Define os valores do coeficiente de ajuste (k);
    3. Localiza e carrega os clusters;
    4. Executa o modelo de estimação para cada cluster de cada cenário;
    5. Combina as estimativas dos clusters utilizando combinação ótima
       baseada na variância;
    6. Calcula o erro da estimativa final;
    7. Salva os resultados individuais e os resultados finais.

Saídas:
    - Resultados_da_estimacao_por_clusters.xlsx
    - Resultados_finais_por_cenario.xlsx

Autor: Matheus Reis de Almeida
"""

import pandas as pd
import numpy as np
import time

from localizar_clusters import localizar_clusters
from carregar_clusters import carregar_clusters
from estimar_pv_clusters import estimar_pv


# ============================================================================
# Inicializa timer

inicio = time.perf_counter()


# ============================================================================
# Etapa 1 - Potência real inserida em cada cenário

df = pd.read_excel(
    "/home/matheus/Documentos/BtM-PV-estimating/logs/Potencias_Cenarios.xlsx"
)

potencias_reais = dict(
    zip(
        df["cenario"],
        df["potencia_PV_kW"]
    )
)


# ============================================================================
# Etapa 2 - Definição dos coeficientes de ajuste

ks = [0.75, 0.8, 0.85, 0.9, 0.95, 1]


# ============================================================================
# Etapa 3 - Localiza e carrega os clusters

arquivos = localizar_clusters()

dados_clusters = carregar_clusters(arquivos)


# ============================================================================
# Etapa 4 - Executa o modelo de estimação

resultados_gerais = []

for k in ks:

    print("=" * 60)
    print(f"\nEstimativa com k = {k:.2f}")

    for cenario, clusters in dados_clusters.items():

        potencia_real = potencias_reais[cenario]

        print(f"\nNível PV = {cenario}%")

        for numero_cluster, df_cluster in clusters.items():

            resultado = estimar_pv(
                df_cluster=df_cluster,
                potencia_real=potencia_real,
                k=k
            )

            # --------------------------------------------------------------
            # Guarda resultados individuais de cada cluster

            resultados_gerais.append(
                {
                    "k": k,
                    "Cenário": cenario,
                    "Cluster": numero_cluster,

                    "Potência Real (kW)": potencia_real,
                    "Potência estimada (kW)": resultado["Pinst"],

                    "Alpha 1": resultado["alpha"][0],
                    "Alpha 2": resultado["alpha"][1],

                    "Variância Pinst": resultado["variancia_Pinst"],
                    "Desvio padrão Pinst": resultado["desvio_padrao_Pinst"],

                    "Cov(alpha1, alpha1)": resultado["cov_alpha"][0, 0],
                    "Cov(alpha1, alpha2)": resultado["cov_alpha"][0, 1],
                    "Cov(alpha2, alpha1)": resultado["cov_alpha"][1, 0],
                    "Cov(alpha2, alpha2)": resultado["cov_alpha"][1, 1],

                    "Sigma²": resultado["sigma2"],

                    "Erro (%)": resultado["erro_percentual"],
                    "Acerto (%)": resultado["acerto"],

                    "RMSE": resultado["RMSE"],
                    "MAE": resultado["MAE"],
                    "R²": resultado["R2"],

                    "Equações": resultado["num_equacoes"],
                    "Graus de liberdade": resultado["graus_liberdade"],
                    "Posto A": resultado["posto_A"],
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


# ============================================================================
# DataFrame com resultados individuais

resultados = pd.DataFrame(resultados_gerais)


# ============================================================================
# Etapa 5 - Combinação ótima das estimativas dos clusters
#
# Para cada cenário:
#
#       w_i = (1 / Var_i) / sum(1 / Var_j)
#
#       P_final = sum(w_i * P_i)
#
# A potência real NÃO é utilizada para determinar os pesos.
# Ela é utilizada somente posteriormente para avaliar o resultado.


resultados_finais = []

for (k, cenario), grupo in resultados.groupby(
    ["k", "Cenário"]
):

    grupo = grupo.copy()

    # ------------------------------------------------------------------------
    # Verifica se todas as variâncias são válidas

    variancias = grupo["Variância Pinst"].to_numpy()

    if (
        np.any(~np.isfinite(variancias))
        or np.any(variancias <= 0)
    ):

        raise ValueError(
            f"Variância inválida para o cenário {cenario} "
            f"com k = {k}."
        )

    # ------------------------------------------------------------------------
    # Pesos baseados no inverso da variância

    precisao = 1.0 / variancias

    pesos = precisao / np.sum(precisao)

    grupo["Peso"] = pesos

    # ------------------------------------------------------------------------
    # Combinação das estimativas

    potencia_estimada = np.sum(
        grupo["Peso"].to_numpy()
        * grupo["Potência estimada (kW)"].to_numpy()
    )

    # ------------------------------------------------------------------------
    # Potência real
    #
    # Utilizada somente para avaliação do resultado final.

    potencia_real = grupo[
        "Potência Real (kW)"
    ].iloc[0]

    # ------------------------------------------------------------------------
    # Erro percentual

    erro_percentual = (
        100
        * abs(potencia_estimada - potencia_real)
        / potencia_real
    )

    acerto = 100 - erro_percentual

    # ------------------------------------------------------------------------
    # Variância da combinação
    #
    # Para a primeira versão, assumimos independência entre as
    # estimativas dos clusters.
    #
    # Var(P_final) = sum(w_i² Var_i)

    variancia_final = np.sum(
        pesos**2 * variancias
    )

    desvio_padrao_final = np.sqrt(
        variancia_final
    )

    # ------------------------------------------------------------------------
    # Guarda resultado final

    resultados_finais.append(
        {
            "k": k,
            "Cenário": cenario,

            "Potência Real (kW)": potencia_real,

            "Potência estimada final (kW)": potencia_estimada,

            "Erro (%)": erro_percentual,
            "Acerto (%)": acerto,

            "Variância final": variancia_final,
            "Desvio padrão final": desvio_padrao_final,

            "Cluster 1": grupo.loc[
                grupo["Cluster"] == 1,
                "Potência estimada (kW)"
            ].iloc[0]
            if 1 in grupo["Cluster"].values else np.nan,

            "Peso C1": grupo.loc[
                grupo["Cluster"] == 1,
                "Peso"
            ].iloc[0]
            if 1 in grupo["Cluster"].values else np.nan,

            "Cluster 2": grupo.loc[
                grupo["Cluster"] == 2,
                "Potência estimada (kW)"
            ].iloc[0]
            if 2 in grupo["Cluster"].values else np.nan,

            "Peso C2": grupo.loc[
                grupo["Cluster"] == 2,
                "Peso"
            ].iloc[0]
            if 2 in grupo["Cluster"].values else np.nan,

            "Cluster 3": grupo.loc[
                grupo["Cluster"] == 3,
                "Potência estimada (kW)"
            ].iloc[0]
            if 3 in grupo["Cluster"].values else np.nan,

            "Peso C3": grupo.loc[
                grupo["Cluster"] == 3,
                "Peso"
            ].iloc[0]
            if 3 in grupo["Cluster"].values else np.nan,

            "Cluster 4": grupo.loc[
                grupo["Cluster"] == 4,
                "Potência estimada (kW)"
            ].iloc[0]
            if 4 in grupo["Cluster"].values else np.nan,

            "Peso C4": grupo.loc[
                grupo["Cluster"] == 4,
                "Peso"
            ].iloc[0]
            if 4 in grupo["Cluster"].values else np.nan,
        }
    )

    # ------------------------------------------------------------------------
    # Exibe resultado final

    print(
        f"\n  >>> RESULTADO FINAL - Cenário {cenario}%"
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

    for _, linha in grupo.sort_values("Cluster").iterrows():

        print(
            f"        C{int(linha['Cluster'])}: "
            f"{linha['Peso']:.4f}"
        )


# ============================================================================
# DataFrame dos resultados finais

finais = pd.DataFrame(resultados_finais)


# ============================================================================
# Etapa 6 - Salva os resultados

caminho_saida = (
    "/home/matheus/Documentos/"
    "Alteracoes_do_modelo_pos_revisao/BtM-PV-estimating_A1/estimador_PV/"
)

resultados.to_excel(
    caminho_saida
    + "Resultados_da_estimacao_por_clusters.xlsx",
    index=False
)

finais.to_excel(
    caminho_saida
    + "Resultados_finais_por_cenario.xlsx",
    index=False
)


# ============================================================================
# Finaliza timer

fim = time.perf_counter()

tempo_total = fim - inicio

minutos = int(
    (tempo_total % 3600) // 60
)

segundos = tempo_total % 60

print()
print("=" * 60)

print(
    f"\nTempo de execução: "
    f"{minutos:02d}:{segundos:05.2f}"
)

print(
    "\nArquivos salvos:"
)

print(
    "  - Resultados_da_estimacao_por_clusters.xlsx"
)

print(
    "  - Resultados_finais_por_cenario.xlsx"
)