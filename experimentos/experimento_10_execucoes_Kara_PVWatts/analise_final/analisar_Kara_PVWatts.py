#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ANÁLISE DOS RESULTADOS DO MODELO DE KARA + PVWatts

Este script analisa os resultados individuais das execuções do modelo
de Kara aplicado com o perfil solar obtido pelo PVWatts.

Estrutura esperada:
    10 execuções
    3 níveis de penetração: 20%, 40%, 60%
    3 janelas: 1 mês, 6 meses, ano
    2 condições: FP=1 e Volt-VAr

Total esperado:
    10 x 3 x 3 x 2 = 180 resultados.

O script:
1. lê os resultados individuais;
2. valida a quantidade de execuções;
3. calcula estatísticas por cenário, janela e condição;
4. calcula estatísticas agregadas por condição e janela;
5. identifica a melhor janela para cada cenário/condição;
6. compara FP=1 e Volt-VAr;
7. verifica a planilha de estatísticas fornecida, quando disponível;
8. gera uma planilha consolidada;
9. gera arquivos CSV;
10. gera gráficos para utilização no artigo.

IMPORTANTE:
- Não seleciona a "melhor execução".
- Todas as 10 execuções são consideradas.
- Os resultados são calculados a partir da estimativa final de cada execução.
"""

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# ============================================================================
# CONFIGURAÇÃO
# ============================================================================

# Altere estes nomes se estiver executando em outra pasta.
ARQUIVO_RESULTADOS = Path(
    "Resultados_Kara_PVWatts_todas_execucoes.xlsx"
)

ARQUIVO_ESTATISTICAS = Path(
    "Estatisticas_Kara_PVWatts.xlsx"
)

OUTPUT_DIR = Path("analysis_results_Kara_PVWatts")


# ============================================================================
# FUNÇÕES AUXILIARES
# ============================================================================

def localizar_arquivo(arquivo: Path, padroes):
    """
    Procura o arquivo informado.
    Se ele não existir, procura arquivos que correspondam aos padrões.
    """
    if arquivo.exists():
        return arquivo

    candidatos = []
    for padrao in padroes:
        candidatos.extend(Path(".").glob(padrao))

    candidatos = sorted(set(candidatos))

    if not candidatos:
        return arquivo

    if len(candidatos) == 1:
        return candidatos[0]

    # Se houver vários, usa o primeiro e informa no terminal.
    print(f"\nAviso: vários arquivos encontrados para {arquivo.name}:")
    for c in candidatos:
        print(f"  - {c}")
    print(f"Usando: {candidatos[0]}")

    return candidatos[0]


def preparar_dados(df):
    """Padroniza tipos e cria variáveis auxiliares."""

    df = df.copy()

    # Tipos numéricos
    colunas_numericas = [
        "potencia_estimada_kW",
        "k_eff",
        "C_eff",
        "C_assinado_Kara",
        "R_kW",
        "RMSE_kW",
        "MAE_kW",
        "R2",
        "variancia_C_eff",
        "desvio_C_eff",
        "numero_observacoes",
        "graus_liberdade",
        "posto",
        "P_PV_media_kW",
        "P_PV_max_kW",
        "P_PV_max_positivo_kW",
        "P_PV_integral_positivo_kWh",
        "potencia_real_kW",
        "erro_percentual",
        "acerto_percentual",
        "Penetracao_percent",
        "Horas_janela",
        "Resolucao_h",
        "Execucao",
    ]

    for coluna in colunas_numericas:
        if coluna in df.columns:
            df[coluna] = pd.to_numeric(
                df[coluna],
                errors="coerce"
            )

    # Booleano
    df["VoltVar"] = (
        df["VoltVar"]
        .astype(str)
        .str.strip()
        .str.lower()
        .map({
            "true": True,
            "false": False,
            "1": True,
            "0": False,
        })
    )

    # Condição em português
    df["Condicao"] = np.where(
        df["VoltVar"],
        "Volt-VAr",
        "FP=1"
    )

    # Penetração numérica
    df["Penetracao"] = df["Penetracao_percent"].astype(int)

    return df


def validar_dados(df):
    """Verifica se a estrutura esperada está presente."""

    obrigatorias = [
        "potencia_estimada_kW",
        "k_eff",
        "C_eff",
        "R_kW",
        "RMSE_kW",
        "MAE_kW",
        "R2",
        "potencia_real_kW",
        "erro_percentual",
        "acerto_percentual",
        "Penetracao_percent",
        "VoltVar",
        "Janela",
        "Execucao",
    ]

    faltantes = [
        c for c in obrigatorias
        if c not in df.columns
    ]

    if faltantes:
        raise ValueError(
            "Colunas obrigatórias não encontradas:\n"
            + "\n".join(f"  - {c}" for c in faltantes)
        )

    # Valores esperados
    penetracoes = sorted(df["Penetracao"].unique())
    janelas = sorted(df["Janela"].unique())
    condicoes = sorted(df["Condicao"].unique())
    execucoes = sorted(df["Execucao"].unique())

    print("\n" + "=" * 90)
    print("VALIDAÇÃO DOS DADOS")
    print("=" * 90)
    print(f"Linhas carregadas: {len(df)}")
    print(f"Execuções: {execucoes}")
    print(f"Penetrações: {penetracoes}")
    print(f"Janelas: {janelas}")
    print(f"Condições: {condicoes}")

    esperadas = 10 * 3 * 3 * 2

    if len(df) != esperadas:
        print(
            f"\nAVISO: eram esperadas {esperadas} linhas, "
            f"mas foram encontradas {len(df)}."
        )
    else:
        print(f"\nQuantidade total correta: {esperadas} linhas.")

    contagem = (
        df
        .groupby(
            ["Condicao", "Penetracao", "Janela"],
            dropna=False
        )
        .size()
        .reset_index(name="N")
    )

    problemas = contagem[contagem["N"] != 10]

    if problemas.empty:
        print("Todas as combinações possuem 10 execuções.")
    else:
        print("\nCombinações com quantidade diferente de 10:")
        print(problemas.to_string(index=False))

    return df


# ============================================================================
# ESTATÍSTICAS PRINCIPAIS
# ============================================================================

def calcular_resumo(df):
    """
    Calcula estatísticas por condição, penetração e janela.
    """

    resumo = (
        df
        .groupby(
            ["Condicao", "Penetracao", "Janela"],
            as_index=False
        )
        .agg(
            Numero_execucoes=(
                "erro_percentual", "count"
            ),

            Potencia_real_kW=(
                "potencia_real_kW", "mean"
            ),

            Potencia_estimada_mean_kW=(
                "potencia_estimada_kW", "mean"
            ),

            Potencia_estimada_std_kW=(
                "potencia_estimada_kW", "std"
            ),

            Potencia_estimada_min_kW=(
                "potencia_estimada_kW", "min"
            ),

            Potencia_estimada_max_kW=(
                "potencia_estimada_kW", "max"
            ),

            Erro_mean_percentual=(
                "erro_percentual", "mean"
            ),

            Erro_std_percentual=(
                "erro_percentual", "std"
            ),

            Erro_min_percentual=(
                "erro_percentual", "min"
            ),

            Erro_max_percentual=(
                "erro_percentual", "max"
            ),

            R2_mean=(
                "R2", "mean"
            ),

            R2_std=(
                "R2", "std"
            ),

            R2_min=(
                "R2", "min"
            ),

            R2_max=(
                "R2", "max"
            ),

            k_eff_mean=(
                "k_eff", "mean"
            ),

            k_eff_std=(
                "k_eff", "std"
            ),

            k_eff_min=(
                "k_eff", "min"
            ),

            k_eff_max=(
                "k_eff", "max"
            ),

            R_mean_kW=(
                "R_kW", "mean"
            ),

            RMSE_mean_kW=(
                "RMSE_kW", "mean"
            ),

            MAE_mean_kW=(
                "MAE_kW", "mean"
            ),
        )
    )

    return resumo


def resumo_por_condicao_janela(df):
    """
    Agrega os três níveis de penetração.
    Cada combinação contém 30 resultados:
    3 cenários x 10 execuções.
    """

    resumo = (
        df
        .groupby(
            ["Condicao", "Janela"],
            as_index=False
        )
        .agg(
            N=("erro_percentual", "count"),
            Erro_medio=("erro_percentual", "mean"),
            Erro_std=("erro_percentual", "std"),
            Erro_min=("erro_percentual", "min"),
            Erro_max=("erro_percentual", "max"),
            R2_medio=("R2", "mean"),
            k_eff_medio=("k_eff", "mean"),
            Potencia_estimada_media=(
                "potencia_estimada_kW", "mean"
            ),
            RMSE_medio=("RMSE_kW", "mean"),
            MAE_medio=("MAE_kW", "mean"),
        )
    )

    return resumo


def melhor_janela_por_cenario(df):
    """
    Identifica a janela com menor erro médio para cada
    condição e nível de penetração.
    """

    tabela = (
        df
        .groupby(
            ["Condicao", "Penetracao", "Janela"],
            as_index=False
        )["erro_percentual"]
        .mean()
        .rename(
            columns={
                "erro_percentual":
                "Erro_medio_percentual"
            }
        )
    )

    indices = (
        tabela
        .groupby(
            ["Condicao", "Penetracao"]
        )["Erro_medio_percentual"]
        .idxmin()
    )

    melhores = (
        tabela
        .loc[indices]
        .sort_values(
            ["Condicao", "Penetracao"]
        )
        .reset_index(drop=True)
    )

    return melhores


# ============================================================================
# COMPARAÇÃO FP=1 x VOLT-VAr
# ============================================================================

def comparar_condicoes(df):
    """
    Compara FP=1 e Volt-VAr para a mesma execução,
    cenário e janela.

    A diferença é:
        erro Volt-VAr - erro FP=1

    Valor negativo:
        Volt-VAr apresentou menor erro.
    """

    base = df[
        [
            "Execucao",
            "Penetracao",
            "Janela",
            "Condicao",
            "erro_percentual",
            "potencia_estimada_kW",
            "R2",
        ]
    ].copy()

    tabela = (
        base
        .pivot_table(
            index=[
                "Execucao",
                "Penetracao",
                "Janela"
            ],
            columns="Condicao",
            values=[
                "erro_percentual",
                "potencia_estimada_kW",
                "R2",
            ],
            aggfunc="first",
        )
    )

    tabela.columns = [
        f"{a}_{b}"
        for a, b in tabela.columns
    ]

    tabela = tabela.reset_index()

    tabela["Diferenca_erro_p.p."] = (
        tabela["erro_percentual_Volt-VAr"]
        - tabela["erro_percentual_FP=1"]
    )

    tabela["Diferenca_potencia_kW"] = (
        tabela["potencia_estimada_kW_Volt-VAr"]
        - tabela["potencia_estimada_kW_FP=1"]
    )

    tabela["Diferenca_R2"] = (
        tabela["R2_Volt-VAr"]
        - tabela["R2_FP=1"]
    )

    return tabela


def resumo_comparacao_condicoes(comparacao):
    """
    Resume a comparação FP=1 x Volt-VAr.
    """

    resumo = (
        comparacao
        .groupby(
            ["Penetracao", "Janela"],
            as_index=False
        )
        .agg(
            N=("Diferenca_erro_p.p.", "count"),

            Erro_medio_FP1=(
                "erro_percentual_FP=1",
                "mean"
            ),

            Erro_medio_VoltVar=(
                "erro_percentual_Volt-VAr",
                "mean"
            ),

            Diferenca_media_erro_p_p=(
                "Diferenca_erro_p.p.",
                "mean"
            ),

            Desvio_diferenca_erro=(
                "Diferenca_erro_p.p.",
                "std"
            ),

            Potencia_media_FP1_kW=(
                "potencia_estimada_kW_FP=1",
                "mean"
            ),

            Potencia_media_VoltVar_kW=(
                "potencia_estimada_kW_Volt-VAr",
                "mean"
            ),

            Diferenca_media_potencia_kW=(
                "Diferenca_potencia_kW",
                "mean"
            ),

            R2_medio_FP1=(
                "R2_FP=1",
                "mean"
            ),

            R2_medio_VoltVar=(
                "R2_Volt-VAr",
                "mean"
            ),
        )
    )

    return resumo


# ============================================================================
# VERIFICAÇÃO CONTRA A PLANILHA DE ESTATÍSTICAS
# ============================================================================

def verificar_planilha_estatisticas(df, arquivo_estatisticas):
    """
    Compara os valores calculados a partir dos 180 resultados
    com a planilha Estatisticas_Kara_PVWatts.xlsx.

    A comparação é feita para:
        - potência estimada média;
        - erro médio;
        - desvio padrão do erro;
        - erro mínimo;
        - erro máximo;
        - R2 médio;
        - k_eff médio.
    """

    if not arquivo_estatisticas.exists():
        print(
            "\nPlanilha de estatísticas não encontrada. "
            "A verificação será ignorada."
        )
        return pd.DataFrame()

    ref = pd.read_excel(
        arquivo_estatisticas,
        sheet_name=0
    )

    # Padroniza nomes
    ref = ref.copy()

    ref["Condicao"] = np.where(
        ref["VoltVar"],
        "Volt-VAr",
        "FP=1"
    )

    # A planilha de estatísticas usa "20", "40", "60"
    # para FP=1 e "20_VV", "40_VV", "60_VV" para Volt-VAr.
    # Quando disponível, Penetracao_percent é preferível.
    if "Penetracao_percent" in ref.columns:
        ref["Penetracao"] = pd.to_numeric(
            ref["Penetracao_percent"],
            errors="coerce"
        )
    else:
        ref["Penetracao"] = pd.to_numeric(
            ref["Cenario"].astype(str).str.extract(r"(\d+)")[0],
            errors="coerce"
        )

    if ref["Penetracao"].isna().any():
        raise ValueError(
            "Não foi possível identificar a penetração "
            "em algumas linhas da planilha de estatísticas."
        )

    ref["Penetracao"] = ref["Penetracao"].astype(int)

    calculado = calcular_resumo(df)

    colunas = [
        "Condicao",
        "Penetracao",
        "Janela",
        "Potencia_estimada_mean_kW",
        "Erro_mean_percentual",
        "Erro_std_percentual",
        "Erro_min_percentual",
        "Erro_max_percentual",
        "R2_mean",
        "k_eff_mean",
    ]

    calc = calculado[colunas].copy()

    ref2 = ref[
        [
            "Condicao",
            "Penetracao",
            "Janela",
            "Potencia_estimada_mean_kW",
            "Erro_mean_percentual",
            "Erro_std_percentual",
            "Erro_min_percentual",
            "Erro_max_percentual",
            "R2_mean",
            "k_eff_mean",
        ]
    ].copy()

    comparacao = calc.merge(
        ref2,
        on=[
            "Condicao",
            "Penetracao",
            "Janela"
        ],
        suffixes=(
            "_calculado",
            "_planilha"
        ),
        how="outer"
    )

    metricas = [
        "Potencia_estimada_mean_kW",
        "Erro_mean_percentual",
        "Erro_std_percentual",
        "Erro_min_percentual",
        "Erro_max_percentual",
        "R2_mean",
        "k_eff_mean",
    ]

    for metrica in metricas:
        comparacao[
            f"Diferenca_{metrica}"
        ] = (
            comparacao[
                f"{metrica}_calculado"
            ]
            -
            comparacao[
                f"{metrica}_planilha"
            ]
        )

    return comparacao


# ============================================================================
# GRÁFICOS
# ============================================================================

def plot_erro_por_janela(df):
    """
    Gráfico do erro médio por janela, separado por condição.
    """

    resumo = resumo_por_condicao_janela(df)

    for condicao in ["FP=1", "Volt-VAr"]:

        dados = resumo[
            resumo["Condicao"] == condicao
        ].copy()

        if dados.empty:
            continue

        ordem = ["1_mes", "6_meses", "ano"]
        dados["Janela_ordem"] = pd.Categorical(
            dados["Janela"],
            categories=ordem,
            ordered=True
        )
        dados = dados.sort_values("Janela_ordem")

        fig, ax = plt.subplots(figsize=(8, 5))

        ax.plot(
            dados["Janela"],
            dados["Erro_medio"],
            marker="o",
            linewidth=2,
        )

        ax.set_xlabel("Janela de dados")
        ax.set_ylabel("Erro médio (%)")
        ax.set_title(
            f"Erro médio por janela — {condicao}"
        )

        ax.grid(True)
        fig.tight_layout()

        nome = (
            "Erro_Medio_Janelas_"
            + condicao.replace("=", "")
                     .replace("-", "_")
            + ".png"
        )

        fig.savefig(
            OUTPUT_DIR / nome,
            dpi=300,
            bbox_inches="tight"
        )

        plt.close(fig)


def plot_erro_por_cenario(df):
    """
    Gráfico do erro médio por penetração e janela.
    """

    resumo = (
        df
        .groupby(
            [
                "Condicao",
                "Penetracao",
                "Janela"
            ],
            as_index=False
        )["erro_percentual"]
        .mean()
    )

    for condicao in ["FP=1", "Volt-VAr"]:

        dados = resumo[
            resumo["Condicao"] == condicao
        ]

        fig, ax = plt.subplots(figsize=(8, 5))

        for janela in ["1_mes", "6_meses", "ano"]:

            serie = dados[
                dados["Janela"] == janela
            ].sort_values("Penetracao")

            ax.plot(
                serie["Penetracao"],
                serie["erro_percentual"],
                marker="o",
                linewidth=2,
                label=janela
            )

        ax.set_xlabel("Penetração PV (%)")
        ax.set_ylabel("Erro médio (%)")
        ax.set_title(
            f"Erro médio por penetração — {condicao}"
        )

        ax.grid(True)
        ax.legend()

        fig.tight_layout()

        nome = (
            "Erro_Medio_Penetracao_"
            + condicao.replace("=", "")
                     .replace("-", "_")
            + ".png"
        )

        fig.savefig(
            OUTPUT_DIR / nome,
            dpi=300,
            bbox_inches="tight"
        )

        plt.close(fig)


def plot_r2_por_cenario(df):
    """
    Gráfico do R² médio por penetração.
    """

    resumo = (
        df
        .groupby(
            [
                "Condicao",
                "Penetracao",
                "Janela"
            ],
            as_index=False
        )["R2"]
        .mean()
    )

    fig, ax = plt.subplots(figsize=(8, 5))

    for condicao in ["FP=1", "Volt-VAr"]:

        for janela in ["1_mes", "6_meses", "ano"]:

            dados = resumo[
                (resumo["Condicao"] == condicao)
                & (resumo["Janela"] == janela)
            ].sort_values("Penetracao")

            ax.plot(
                dados["Penetracao"],
                dados["R2"],
                marker="o",
                linewidth=1.5,
                label=f"{condicao} — {janela}"
            )

    ax.set_xlabel("Penetração PV (%)")
    ax.set_ylabel("R² médio")
    ax.set_title("R² médio por penetração e janela")

    ax.grid(True)
    ax.legend(fontsize=8)

    fig.tight_layout()

    fig.savefig(
        OUTPUT_DIR / "R2_Medio_Penetracao_Janela.png",
        dpi=300,
        bbox_inches="tight"
    )

    plt.close(fig)


def plot_k_eff(df):
    """
    Gráfico do k_eff médio por penetração.
    """

    resumo = (
        df
        .groupby(
            [
                "Condicao",
                "Penetracao",
                "Janela"
            ],
            as_index=False
        )["k_eff"]
        .mean()
    )

    fig, ax = plt.subplots(figsize=(8, 5))

    for condicao in ["FP=1", "Volt-VAr"]:

        dados = resumo[
            resumo["Condicao"] == condicao
        ]

        for janela in ["1_mes", "6_meses", "ano"]:

            serie = dados[
                dados["Janela"] == janela
            ].sort_values("Penetracao")

            ax.plot(
                serie["Penetracao"],
                serie["k_eff"],
                marker="o",
                linewidth=1.5,
                label=f"{condicao} — {janela}"
            )

    ax.set_xlabel("Penetração PV (%)")
    ax.set_ylabel(r"$k_{\mathrm{eff}}$")
    ax.set_title(
        r"Coeficiente $k_{\mathrm{eff}}$ médio"
    )

    ax.grid(True)
    ax.legend(fontsize=8)

    fig.tight_layout()

    fig.savefig(
        OUTPUT_DIR / "k_eff_Medio_Penetracao_Janela.png",
        dpi=300,
        bbox_inches="tight"
    )

    plt.close(fig)


# ============================================================================
# IMPRESSÃO DOS RESULTADOS
# ============================================================================

def imprimir_resultados(df):

    resumo = calcular_resumo(df)

    print("\n" + "=" * 100)
    print("ANÁLISE DO MODELO DE KARA + PVWATTS")
    print("=" * 100)

    # ------------------------------------------------------------------------
    # Resumo completo
    # ------------------------------------------------------------------------

    print("\nRESUMO POR CONDIÇÃO, PENETRAÇÃO E JANELA")
    print("-" * 100)

    tabela = resumo[
        [
            "Condicao",
            "Penetracao",
            "Janela",
            "Numero_execucoes",
            "Erro_mean_percentual",
            "Erro_std_percentual",
            "Erro_min_percentual",
            "Erro_max_percentual",
            "R2_mean",
            "k_eff_mean",
        ]
    ].copy()

    print(
        tabela.to_string(index=False)
    )

    # ------------------------------------------------------------------------
    # Resumo por condição e janela
    # ------------------------------------------------------------------------

    print("\n" + "=" * 100)
    print("RESUMO POR CONDIÇÃO E JANELA")
    print("=" * 100)

    resumo_cj = resumo_por_condicao_janela(df)

    print(
        resumo_cj.to_string(index=False)
    )

    # ------------------------------------------------------------------------
    # Melhor janela
    # ------------------------------------------------------------------------

    print("\n" + "=" * 100)
    print("MELHOR JANELA POR CONDIÇÃO E PENETRAÇÃO")
    print("=" * 100)

    melhores = melhor_janela_por_cenario(df)

    print(
        melhores.to_string(index=False)
    )

    # ------------------------------------------------------------------------
    # Comparação FP1 x Volt-VAr
    # ------------------------------------------------------------------------

    print("\n" + "=" * 100)
    print("COMPARAÇÃO FP=1 x VOLT-VAr")
    print("=" * 100)

    comparacao = comparar_condicoes(df)

    resumo_comp = resumo_comparacao_condicoes(
        comparacao
    )

    print(
        resumo_comp.to_string(index=False)
    )

    # ------------------------------------------------------------------------
    # Melhor combinação geral
    # ------------------------------------------------------------------------

    print("\n" + "=" * 100)
    print("MENOR ERRO MÉDIO ENTRE TODAS AS COMBINAÇÕES")
    print("=" * 100)

    idx = (
        resumo["Erro_mean_percentual"]
        .idxmin()
    )

    melhor = resumo.loc[idx]

    print(
        f"Condição : {melhor['Condicao']}"
    )
    print(
        f"Penetração: {int(melhor['Penetracao'])}%"
    )
    print(
        f"Janela   : {melhor['Janela']}"
    )
    print(
        f"Erro médio: "
        f"{melhor['Erro_mean_percentual']:.3f}%"
    )

    # ------------------------------------------------------------------------
    # Média global por condição
    # ------------------------------------------------------------------------

    print("\n" + "=" * 100)
    print("MÉDIA GLOBAL POR CONDIÇÃO")
    print("=" * 100)

    global_condicao = (
        df
        .groupby("Condicao")
        .agg(
            N=("erro_percentual", "count"),
            Erro_medio=("erro_percentual", "mean"),
            Erro_std=("erro_percentual", "std"),
            Erro_min=("erro_percentual", "min"),
            Erro_max=("erro_percentual", "max"),
            R2_medio=("R2", "mean"),
            k_eff_medio=("k_eff", "mean"),
        )
        .reset_index()
    )

    print(
        global_condicao.to_string(index=False)
    )


# ============================================================================
# SALVAMENTO
# ============================================================================

def salvar_resultados(
    df,
    arquivo_verificacao
):

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    resumo = calcular_resumo(df)
    resumo_cj = resumo_por_condicao_janela(df)
    melhores = melhor_janela_por_cenario(df)

    comparacao = comparar_condicoes(df)
    resumo_comp = resumo_comparacao_condicoes(
        comparacao
    )

    global_condicao = (
        df
        .groupby("Condicao")
        .agg(
            N=("erro_percentual", "count"),
            Erro_medio=("erro_percentual", "mean"),
            Erro_std=("erro_percentual", "std"),
            Erro_min=("erro_percentual", "min"),
            Erro_max=("erro_percentual", "max"),
            R2_medio=("R2", "mean"),
            k_eff_medio=("k_eff", "mean"),
        )
        .reset_index()
    )

    verificacao = verificar_planilha_estatisticas(
        df,
        arquivo_verificacao
    )

    excel = (
        OUTPUT_DIR
        / "Analise_Kara_PVWatts.xlsx"
    )

    with pd.ExcelWriter(
        excel,
        engine="openpyxl"
    ) as writer:

        df.to_excel(
            writer,
            sheet_name="Resultados_Individuais",
            index=False
        )

        resumo.to_excel(
            writer,
            sheet_name="Resumo_Cenario_Janela",
            index=False
        )

        resumo_cj.to_excel(
            writer,
            sheet_name="Resumo_Condicao_Janela",
            index=False
        )

        melhores.to_excel(
            writer,
            sheet_name="Melhor_Janela",
            index=False
        )

        comparacao.to_excel(
            writer,
            sheet_name="Comparacao_FP1_VV",
            index=False
        )

        resumo_comp.to_excel(
            writer,
            sheet_name="Resumo_FP1_VV",
            index=False
        )

        global_condicao.to_excel(
            writer,
            sheet_name="Resumo_Global",
            index=False
        )

        if not verificacao.empty:
            verificacao.to_excel(
                writer,
                sheet_name="Verificacao_Estatisticas",
                index=False
            )

    # CSVs
    resumo.to_csv(
        OUTPUT_DIR / "Resumo_Cenario_Janela.csv",
        index=False
    )

    resumo_cj.to_csv(
        OUTPUT_DIR / "Resumo_Condicao_Janela.csv",
        index=False
    )

    melhores.to_csv(
        OUTPUT_DIR / "Melhor_Janela.csv",
        index=False
    )

    resumo_comp.to_csv(
        OUTPUT_DIR / "Resumo_FP1_VV.csv",
        index=False
    )

    global_condicao.to_csv(
        OUTPUT_DIR / "Resumo_Global.csv",
        index=False
    )

    if not verificacao.empty:
        verificacao.to_csv(
            OUTPUT_DIR / "Verificacao_Estatisticas.csv",
            index=False
        )

    return excel


# ============================================================================
# MAIN
# ============================================================================

def main():

    arquivo_resultados = localizar_arquivo(
        ARQUIVO_RESULTADOS,
        [
            "*Resultados_Kara_PVWatts*todas*execucoes*.xlsx",
            "*Resultados_Kara_PVWatts*.xlsx",
        ]
    )

    arquivo_estatisticas = localizar_arquivo(
        ARQUIVO_ESTATISTICAS,
        [
            "*Estatisticas_Kara_PVWatts*.xlsx",
        ]
    )

    if not arquivo_resultados.exists():
        raise FileNotFoundError(
            f"Arquivo de resultados não encontrado:\n"
            f"{arquivo_resultados.resolve()}"
        )

    print("=" * 90)
    print("ANÁLISE DOS RESULTADOS KARA + PVWATTS")
    print("=" * 90)
    print(f"\nArquivo de resultados:")
    print(arquivo_resultados.resolve())

    if arquivo_estatisticas.exists():
        print("\nArquivo de estatísticas:")
        print(arquivo_estatisticas.resolve())

    df = pd.read_excel(
        arquivo_resultados,
        sheet_name=0
    )

    df = preparar_dados(df)
    df = validar_dados(df)

    imprimir_resultados(df)

    excel = salvar_resultados(
        df,
        arquivo_estatisticas
    )

    # Gráficos
    plot_erro_por_janela(df)
    plot_erro_por_cenario(df)
    plot_r2_por_cenario(df)
    plot_k_eff(df)

    print("\n" + "=" * 90)
    print("ANÁLISE CONCLUÍDA")
    print("=" * 90)
    print(f"\nResultados salvos em:")
    print(OUTPUT_DIR.resolve())
    print(f"\nPlanilha principal:")
    print(excel.resolve())


if __name__ == "__main__":
    main()
