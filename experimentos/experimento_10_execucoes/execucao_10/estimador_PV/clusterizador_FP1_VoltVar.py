#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Clusterização dos resultados das simulações PV
------------------------------------------------

Processa separadamente:

    FP1
        resultados20.parquet
        resultados40.parquet
        resultados60.parquet

    Volt-VAr
        resultados20_VV.parquet
        resultados40_VV.parquet
        resultados60_VV.parquet

A lógica de clusterização é mantida conforme o clusterizador original:
    - período 06:00 às 18:00
    - variável de clusterização = Q_kvar
    - KMeans
    - 4 clusters
    - random_state = 42
    - n_init = 10

A principal alteração é a identificação da condição da simulação e a
separação dos arquivos de saída em:

    dados/outputs/clusters/FP1/
    dados/outputs/clusters/VoltVar/

Assim, os resultados das duas condições não se misturam.

@author: Matheus
"""

import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.cluster import KMeans
from matplotlib import pyplot as plt
from os import system
import sys

ROOT = Path(__file__).resolve().parent.parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import configs as cfg

system("clear")


# ==========================================================
# CONFIGURAÇÕES
# ==========================================================

N_CLUSTERS = 4

# Variável utilizada na clusterização
VARIAVEL_CLUSTER = "Q_kvar"

VARIAVEIS_VALIDAS = [
    "P_kW",
    "Q_kvar",
    "irradiancia_W_m2",
    "temperatura"
]

# Condições que serão processadas
CONDICOES_VALIDAS = [
    "FP1",
    "VoltVar"
]


# ==========================================================
# PASTAS
# ==========================================================

# Resultados das simulações
PASTA_RESULTADOS = cfg.OUT_PV

# Dados climáticos
ARQUIVO_CLIMA = cfg.CLIMA_PROCESSADOS

# Pasta geral dos clusters
PASTA_CLUSTERS = cfg.OUTPUTS_DIR / "clusters"

# Uma pasta independente para cada condição
PASTA_FP1 = PASTA_CLUSTERS / "FP1"
PASTA_VV = PASTA_CLUSTERS / "VoltVar"


# ==========================================================
# IDENTIFICA A CONDIÇÃO DO ARQUIVO
# ==========================================================

def identificar_resultado(arquivo):
    """
    Identifica o nível de penetração e a condição da simulação.

    Exemplos:
        resultados20.parquet
            -> nivel = "20"
            -> condicao = "FP1"

        resultados20_VV.parquet
            -> nivel = "20"
            -> condicao = "VoltVar"
    """

    nome = arquivo.stem

    if not nome.startswith("resultados"):
        return None

    nivel = nome.replace("resultados", "", 1)

    if nivel.endswith("_VV"):
        nivel = nivel[:-3]
        condicao = "VoltVar"
    else:
        condicao = "FP1"

    if not nivel.isdigit():
        return None

    return {
        "nivel": nivel,
        "condicao": condicao,
        "arquivo": arquivo
    }


# ==========================================================
# LOCALIZA OS RESULTADOS DAS SIMULAÇÕES
# ==========================================================

def localizar_resultados():
    print("\n" + "=" * 70)
    print("LOCALIZAÇÃO DOS RESULTADOS DAS SIMULAÇÕES")
    print("=" * 70)

    resultados = []

    arquivos = sorted(
        PASTA_RESULTADOS.glob("resultados*.parquet")
    )

    for arquivo in arquivos:

        resultado = identificar_resultado(arquivo)

        if resultado is not None:
            resultados.append(resultado)

    if not resultados:
        raise FileNotFoundError(
            f"Nenhum arquivo 'resultados*.parquet' encontrado em:\n"
            f"{PASTA_RESULTADOS}"
        )

    # Ordena por condição e nível
    ordem_condicao = {
        "FP1": 0,
        "VoltVar": 1
    }

    resultados.sort(
        key=lambda x: (
            ordem_condicao.get(x["condicao"], 99),
            int(x["nivel"])
        )
    )

    print(f"\nForam encontrados {len(resultados)} arquivos:")

    for resultado in resultados:
        print(
            f"  [{resultado['condicao']:7s}] "
            f"{resultado['nivel']:>3s}% -> "
            f"{resultado['arquivo'].name}"
        )

    print("-" * 70)

    return resultados


# ==========================================================
# CARREGA OS RESULTADOS
# ==========================================================

def ler_resultados(lista_resultados):
    print("\nLeitura dos resultados\n")

    resultados = {}

    for cenario in lista_resultados:

        chave = (
            cenario["condicao"],
            cenario["nivel"]
        )

        print(
            f"{cenario['condicao']} - "
            f"Cenário {cenario['nivel']}%"
        )

        df = pd.read_parquet(
            cenario["arquivo"]
        )

        resultados[chave] = df

        print(
            f"   Registros carregados: {len(df)}"
        )

    print(
        f"\nForam carregados "
        f"{len(resultados)} cenários."
    )

    print("-" * 70)

    return resultados


# ==========================================================
# CARREGA DADOS CLIMÁTICOS
# ==========================================================

def ler_dados_climaticos():

    print("\nLeitura dos dados climáticos\n")

    df = pd.read_excel(
        ARQUIVO_CLIMA
    )

    print(
        f"Foram carregados "
        f"{len(df)} registros."
    )

    print("-" * 70)

    return df


# ==========================================================
# FILTRA PERÍODO DIURNO
# ==========================================================

def filtrar_periodo_diurno(
        resultados,
        clima
        ):

    print(
        "\nFiltrando período entre 06:00 e 18:00..."
    )

    resultados_filtrados = {}

    for chave, df in resultados.items():

        condicao, nivel = chave

        dados = df.copy()

        # Identifica o dia
        dados["dia"] = (
            dados["hora"] // 24
        )

        # Converte para hora do dia
        dados["hora"] = (
            dados["hora"] % 24
        )

        # Mantém somente 06:00 até 18:00
        dados = dados.loc[
            (dados["hora"] >= 6) &
            (dados["hora"] <= 18)
        ].copy()

        dados = dados.sort_values(
            ["dia", "hora"]
        ).reset_index(drop=True)

        resultados_filtrados[
            chave
        ] = dados

    # Filtra os dados climáticos
    clima = clima.copy()

    clima = clima.loc[
        (clima["hora"] >= 6) &
        (clima["hora"] <= 18)
    ].copy()

    clima = clima.reset_index(drop=True)

    print(
        f"\nRegistros climáticos após "
        f"filtragem: {len(clima)}"
    )

    print("-" * 70)

    return resultados_filtrados, clima


# ==========================================================
# JUNTA RESULTADOS + CLIMA
# ==========================================================

def organizar_dados(
        resultados,
        clima
        ):

    print(
        "\nOrganizando os cenários...\n"
    )

    cenarios = {}

    for chave, df in resultados.items():

        condicao, nivel = chave

        dados = df.copy()

        # Verificação para evitar associação silenciosa
        # de clima com quantidade diferente de registros.
        if len(dados) != len(clima):
            raise ValueError(
                f"Quantidade de registros incompatível.\n"
                f"Condição: {condicao}\n"
                f"Nível: {nivel}%\n"
                f"Simulação: {len(dados)} registros\n"
                f"Clima: {len(clima)} registros"
            )

        # Adiciona irradiância
        dados["irradiancia_W_m2"] = (
            clima["irradiancia_W_m2"].values
        )

        # Adiciona temperatura
        dados["temperatura"] = (
            clima["temperatura"].values
        )

        # Organiza por dia e hora
        dados = dados.sort_values(
            ["dia", "hora"]
        ).reset_index(
            drop=True
        )

        print(
            f"{condicao} - {nivel}%"
        )

        print(
            f" Dias encontrados : "
            f"{dados['dia'].nunique()}"
        )

        print(
            f" Registros        : "
            f"{len(dados)}"
        )

        cenarios[chave] = dados

    print("-" * 70)

    return cenarios


# ==========================================================
# ORGANIZA CURVAS DIÁRIAS
# ==========================================================

def organizar_curvas_diarias(
        resultados,
        variavel=VARIAVEL_CLUSTER
        ):

    if variavel not in VARIAVEIS_VALIDAS:
        raise ValueError(
            f"Variável '{variavel}' inválida.\n"
            f"Escolha uma entre:\n"
            f"{VARIAVEIS_VALIDAS}"
        )

    print(
        f"\nOrganizando curvas diárias de "
        f"{variavel}\n"
    )

    curvas = {}

    for chave, df in resultados.items():

        condicao, nivel = chave

        dados = df.copy()

        # Cada dia possui 13 pontos:
        # 06, 07, ..., 18
        if len(dados) % 13 != 0:
            raise ValueError(
                f"O cenário {condicao} {nivel}% possui "
                f"{len(dados)} registros diurnos, "
                f"que não são múltiplos de 13."
            )

        dados["dia_curva"] = (
            np.arange(len(dados)) // 13
        )

        matriz = (
            dados
            .pivot(
                index="dia_curva",
                columns="hora",
                values=variavel
            )
            .sort_index(axis=1)
        )

        # Garante exatamente as 13 horas esperadas
        horas_esperadas = list(range(6, 19))

        horas_encontradas = list(matriz.columns)

        if horas_encontradas != horas_esperadas:
            raise ValueError(
                f"Horas incompletas ou inesperadas em "
                f"{condicao} {nivel}%.\n"
                f"Esperadas: {horas_esperadas}\n"
                f"Encontradas: {horas_encontradas}"
            )

        curvas[chave] = matriz

        print(
            f"{condicao} - {nivel}%: "
            f"{matriz.shape[0]} dias x "
            f"{matriz.shape[1]} horas"
        )

    print("-" * 70)

    return curvas


# ==========================================================
# REALIZA A CLUSTERIZAÇÃO
# ==========================================================

def clusterizar_curvas(
        curvas,
        n_clusters=N_CLUSTERS
        ):

    print(
        "\nIniciando clusterização...\n"
    )

    resultados_cluster = {}

    for chave, matriz in curvas.items():

        condicao, nivel = chave

        print(
            f"{condicao} - Cenário {nivel}%..."
        )

        modelo = KMeans(
            n_clusters=n_clusters,
            random_state=42,
            n_init=10
        )

        labels = modelo.fit_predict(
            matriz
        )

        resultados_cluster[chave] = {
            "labels": labels,
            "centroides":
                modelo.cluster_centers_,
            "inercia":
                modelo.inertia_,
            "modelo":
                modelo,
            "curvas":
                matriz,
            "n_clusters":
                n_clusters
        }

        print(
            f"   Foram encontrados "
            f"{n_clusters} clusters."
        )

        print(
            f"   Inércia: "
            f"{modelo.inertia_:.2f}"
        )

    print("-" * 70)

    return resultados_cluster


# ==========================================================
# PLOTA OS CLUSTERS
# ==========================================================

def plota_clusters(
        resultados_cluster
        ):

    print(
        "\nGerando gráficos dos clusters...\n"
    )

    for chave, dados in resultados_cluster.items():

        condicao, nivel = chave

        pasta = (
            PASTA_FP1 / "figuras"
            if condicao == "FP1"
            else PASTA_VV / "figuras"
        )

        pasta.mkdir(
            parents=True,
            exist_ok=True
        )

        curvas = dados["curvas"]
        labels = dados["labels"]
        centroides = dados["centroides"]

        horas = curvas.columns

        n_clusters = len(
            centroides
        )

        for cluster in range(n_clusters):

            plt.figure(
                figsize=(10, 6)
            )

            dias = curvas.iloc[
                labels == cluster
            ]

            # Curvas pertencentes ao cluster
            for _, curva in dias.iterrows():

                plt.plot(
                    horas,
                    curva.values,
                    color="lightgray",
                    linewidth=0.8,
                    alpha=0.8
                )

            # Centróide
            plt.plot(
                horas,
                centroides[cluster],
                color="red",
                linewidth=3,
                label="Centróide"
            )

            plt.title(
                f"{condicao} - Cenário {nivel}% - "
                f"Cluster {cluster + 1} "
                f"({len(dias)} dias)"
            )

            plt.xlabel(
                "Hora"
            )

            plt.ylabel(
                VARIAVEL_CLUSTER
            )

            plt.xticks(
                horas
            )

            plt.grid(
                True,
                linestyle="--",
                alpha=0.4
            )

            plt.legend()

            plt.tight_layout()

            nome = (
                f"Cluster_{cluster + 1}_"
                f"{nivel}.png"
            )

            plt.savefig(
                pasta / nome,
                dpi=300
            )

            plt.show()
            plt.close()

    print(
        "\nFiguras salvas nas pastas correspondentes."
    )

    print("-" * 70)


# ==========================================================
# SEPARA OS DADOS POR CLUSTER
# ==========================================================

def separar_dados_clusters(
        resultados_cluster,
        resultados
        ):

    print(
        "\nSeparando os dados por cluster...\n"
    )

    dados_clusters = {}

    for chave, dados_cluster_info in resultados_cluster.items():

        condicao, nivel = chave

        df = resultados[chave].copy()

        labels = dados_cluster_info["labels"]
        curvas = dados_cluster_info["curvas"]

        dias = curvas.index

        n_clusters = len(
            dados_cluster_info["centroides"]
        )

        dados_clusters[chave] = {}

        for cluster in range(n_clusters):

            dias_cluster = (
                dias[
                    labels == cluster
                ]
            )

            # A coluna dia foi criada antes da organização
            # das curvas e continua identificando o dia original.
            df_cluster = df.loc[
                df["dia"].isin(
                    dias_cluster
                )
            ].copy()

            dados_clusters[
                chave
            ][cluster] = df_cluster

            print(
                f"{condicao} - {nivel}% - "
                f"Cluster {cluster + 1}: "
                f"{len(dias_cluster)} dias"
            )

    print("-" * 70)

    return dados_clusters


# ==========================================================
# CALCULA POTÊNCIA MÉDIA DOS CLUSTERS
# ==========================================================

def potencia_media_clusters(
        resultados_cluster
        ):

    print(
        "\nPotência reativa média "
        "de cada cluster\n"
    )

    for chave, dados in resultados_cluster.items():

        condicao, nivel = chave

        curvas = dados["curvas"]
        labels = dados["labels"]

        n_clusters = len(
            dados["centroides"]
        )

        print(
            f"Condição: {condicao} | "
            f"Nível PV: {nivel}%"
        )

        for cluster in range(n_clusters):

            dias = curvas.iloc[
                labels == cluster
            ]

            print()

            print(
                f"  Cluster {cluster + 1}: "
                f"Média = {dias.values.mean():.2f} kvar | "
                f"Mín = {dias.values.min():.2f} kvar | "
                f"Máx = {dias.values.max():.2f} kvar | "
                f"{len(dias)} dias"
            )

    print("-" * 70)


# ==========================================================
# SALVA OS CLUSTERS
# ==========================================================

def salvar_clusters(
        dados_clusters,
        resultados_cluster
        ):

    print(
        "\nSalvando arquivos dos clusters...\n"
    )

    for chave, clusters in dados_clusters.items():

        condicao, nivel = chave

        if condicao == "FP1":
            pasta_saida = PASTA_FP1
        elif condicao == "VoltVar":
            pasta_saida = PASTA_VV
        else:
            raise ValueError(
                f"Condição desconhecida: {condicao}"
            )

        pasta_saida.mkdir(
            parents=True,
            exist_ok=True
        )

        # ==================================================
        # Salva a relação dos dias pertencentes aos clusters
        # ==================================================

        labels = resultados_cluster[
            chave
        ]["labels"]

        dias = resultados_cluster[
            chave
        ]["curvas"].index

        n_clusters = len(
            resultados_cluster[
                chave
            ]["centroides"]
        )

        dias_clusters = {}

        for cluster in range(n_clusters):

            dias_cluster = dias[
                labels == cluster
            ]

            dias_clusters[
                f"Cluster {cluster + 1}"
            ] = pd.Series(
                dias_cluster
            )

        df_dias = pd.DataFrame(
            dias_clusters
        )

        if condicao == "FP1":
            nome_dias = (
                f"Dias_Clusters_{nivel}.xlsx"
            )
        else:
            nome_dias = (
                f"Dias_Clusters_{nivel}_VV.xlsx"
            )

        arquivo_dias = (
            pasta_saida / nome_dias
        )

        df_dias.to_excel(
            arquivo_dias,
            index=False
        )

        # ==================================================
        # Salva os dados de cada cluster
        # ==================================================

        for cluster, df in clusters.items():

            if condicao == "FP1":
                nome_base = (
                    f"Cluster_{cluster + 1}_"
                    f"{nivel}"
                )
            else:
                nome_base = (
                    f"Cluster_{cluster + 1}_"
                    f"{nivel}_VV"
                )

            arquivo_parquet = (
                pasta_saida /
                f"{nome_base}.parquet"
            )

            arquivo_excel = (
                pasta_saida /
                f"{nome_base}.xlsx"
            )

            df.to_parquet(
                arquivo_parquet,
                index=False
            )

            df.to_excel(
                arquivo_excel,
                index=False
            )

            print(
                f"{condicao} - Cenário {nivel}% - "
                f"Cluster {cluster + 1}"
            )

            print(
                f" Número de linhas: "
                f"{len(df)}"
            )

            print(
                f" Arquivo: "
                f"{arquivo_parquet}"
            )

        print(
            f"Arquivo salvo: "
            f"{arquivo_dias}"
        )

        print()

    print(
        f"Clusters FP1 salvos em:\n"
        f"{PASTA_FP1}"
    )

    print(
        f"\nClusters Volt-VAr salvos em:\n"
        f"{PASTA_VV}"
    )

    print("-" * 70)


# ==========================================================
# RESUMO DOS ARQUIVOS ENCONTRADOS
# ==========================================================

def validar_cenarios(lista_resultados):

    niveis_esperados = {"20", "40", "60"}

    encontrados = {
        "FP1": set(),
        "VoltVar": set()
    }

    for item in lista_resultados:
        encontrados[
            item["condicao"]
        ].add(item["nivel"])

    print("\nValidação dos cenários")

    for condicao in CONDICOES_VALIDAS:

        niveis = encontrados[condicao]

        print(
            f"  {condicao}: "
            f"{sorted(niveis, key=int) if niveis else 'nenhum'}"
        )

        faltantes = (
            niveis_esperados - niveis
        )

        if faltantes:
            print(
                f"    ATENÇÃO: faltam "
                f"{sorted(faltantes, key=int)}"
            )

    print("-" * 70)


# ==========================================================
# FUNÇÃO PRINCIPAL
# ==========================================================

def main():

    # ------------------------------------------------------
    # 1. Localiza os resultados
    # ------------------------------------------------------

    lista = localizar_resultados()

    validar_cenarios(lista)


    # ------------------------------------------------------
    # 2. Carrega os resultados
    # ------------------------------------------------------

    resultados = ler_resultados(
        lista
    )


    # ------------------------------------------------------
    # 3. Carrega os dados climáticos
    # ------------------------------------------------------

    clima = ler_dados_climaticos()


    # ------------------------------------------------------
    # 4. Filtra período diurno
    # ------------------------------------------------------

    resultados, clima = (
        filtrar_periodo_diurno(
            resultados,
            clima
        )
    )


    # ------------------------------------------------------
    # 5. Junta resultados e clima
    # ------------------------------------------------------

    cenarios = organizar_dados(
        resultados,
        clima
    )


    # ------------------------------------------------------
    # 6. Organiza as curvas diárias
    # ------------------------------------------------------

    curvas = organizar_curvas_diarias(
        cenarios,
        variavel=VARIAVEL_CLUSTER
    )


    # ------------------------------------------------------
    # 7. Realiza a clusterização
    # ------------------------------------------------------

    resultados_cluster = clusterizar_curvas(
        curvas,
        n_clusters=N_CLUSTERS
    )


    # ------------------------------------------------------
    # 8. Gera os gráficos
    # ------------------------------------------------------

    plota_clusters(
        resultados_cluster
    )


    # ------------------------------------------------------
    # 9. Calcula estatísticas dos clusters
    # ------------------------------------------------------

    potencia_media_clusters(
        resultados_cluster
    )


    # ------------------------------------------------------
    # 10. Separa os dados por cluster
    # ------------------------------------------------------

    dados_clusters = separar_dados_clusters(
        resultados_cluster,
        cenarios
    )


    # ------------------------------------------------------
    # 11. Salva os clusters
    # ------------------------------------------------------

    salvar_clusters(
        dados_clusters,
        resultados_cluster
    )


    # ------------------------------------------------------
    # Final
    # ------------------------------------------------------

    print("\n" + "=" * 70)
    print("CLUSTERIZAÇÃO CONCLUÍDA")
    print("=" * 70)

    print(
        "\nCondições processadas:"
    )

    print(
        "  FP1      -> "
        f"{PASTA_FP1}"
    )

    print(
        "  Volt-VAr -> "
        f"{PASTA_VV}"
    )

    print(
        "\nA metodologia de clusterização foi mantida."
    )

    print("=" * 70)


# ==========================================================
# EXECUÇÃO
# ==========================================================

if __name__ == "__main__":
    main()
