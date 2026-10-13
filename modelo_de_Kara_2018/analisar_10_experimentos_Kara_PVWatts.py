#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
KARA + PVWATTS
Análise estatística das 10 execuções independentes.

IMPORTANTE:
- Este script NÃO executa simulações.
- Ele lê os arquivos produzidos pelo estimador Kara.
- Os nomes das colunas são os nomes realmente utilizados pelo estimador:
    potencia_estimada_kW
    erro_percentual
    k_eff
    C_eff
    R_kW
    R2
    RMSE_kW
    MAE_kW
    etc.

Estrutura esperada:

experimentos/
└── experimento_10_execucoes_Kara_PVWatts/
    ├── execucao_01/
    │   └── modelo_de_Kara_2018/
    │       └── Resultados_Kara_PVWatts_FP1_VoltVar.xlsx
    ├── ...
    └── execucao_10/

Saídas:

analise_final/
├── Resultados_Kara_PVWatts_todas_execucoes.xlsx
├── Estatisticas_Kara_PVWatts.xlsx
├── Estatisticas_Kara_PVWatts.csv
├── Resumo_Kara_PVWatts.txt
├── Potencia_Real_vs_Estimada_10_Execucoes.png
└── Erro_por_Execucao.png
"""

from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt


# ============================================================================
# CONFIGURAÇÃO
# ============================================================================

PROJECT_ROOT = Path(
    "/home/matheus/Documentos/BtM-PV-estimating_BKP_3/"
    "BtM-PV-estimating_A1_VoltVar"
).resolve()

EXPERIMENT_ROOT = (
    PROJECT_ROOT
    / "experimentos"
    / "experimento_10_execucoes_Kara_PVWatts"
).resolve()

N_EXECUCOES = 10

PASTA_ANALISE = (
    EXPERIMENT_ROOT
    / "analise_final"
)


# ============================================================================
# AUXILIARES
# ============================================================================

def print_header(text):
    print()
    print("=" * 78)
    print(text)
    print("=" * 78)


def localizar_planilha(pasta_execucao):
    """Localiza a planilha principal gerada pelo estimador Kara."""

    pasta_kara = (
        pasta_execucao
        / "modelo_de_Kara_2018"
    )

    arquivo_principal = (
        pasta_kara
        / "Resultados_Kara_PVWatts_FP1_VoltVar.xlsx"
    )

    if arquivo_principal.exists():
        return arquivo_principal

    # Fallback: procura qualquer resultado Kara + PVWatts.
    encontrados = sorted(
        pasta_kara.glob(
            "Resultados_Kara_PVWatts*.xlsx"
        )
    )

    if encontrados:
        return encontrados[0]

    return None


# ============================================================================
# COLETA DOS RESULTADOS
# ============================================================================

def coletar_resultados():

    print_header(
        "COLETANDO RESULTADOS DAS 10 EXECUÇÕES"
    )

    if not EXPERIMENT_ROOT.exists():
        raise FileNotFoundError(
            "Pasta de experimentos não encontrada:\n"
            f"{EXPERIMENT_ROOT}"
        )

    frames = []
    status = []

    for numero in range(
        1,
        N_EXECUCOES + 1
    ):

        pasta_execucao = (
            EXPERIMENT_ROOT
            / f"execucao_{numero:02d}"
        )

        if not pasta_execucao.exists():

            print(
                f"[MISSING] Execução {numero:02d}: "
                "pasta não encontrada."
            )

            status.append(
                (numero, "MISSING")
            )

            continue

        arquivo = localizar_planilha(
            pasta_execucao
        )

        if arquivo is None:

            print(
                f"[MISSING] Execução {numero:02d}: "
                "resultado Kara não encontrado."
            )

            status.append(
                (numero, "NO_RESULT")
            )

            continue

        try:

            df = pd.read_excel(
                arquivo
            )

            df["Execucao"] = numero
            df["Arquivo_origem"] = str(
                arquivo
            )

            frames.append(df)

            print(
                f"[OK] Execução {numero:02d}: "
                f"{len(df)} resultados"
            )

            status.append(
                (numero, "SUCCESS")
            )

        except Exception as exc:

            print(
                f"[ERROR] Execução {numero:02d}: "
                f"{exc}"
            )

            status.append(
                (numero, "ERROR")
            )

    if not frames:
        raise RuntimeError(
            "Nenhum resultado Kara foi encontrado."
        )

    todos = pd.concat(
        frames,
        ignore_index=True
    )

    return todos, status


# ============================================================================
# PREPARAÇÃO
# ============================================================================

def preparar_colunas(todos):

    """
    Ajusta somente os identificadores necessários para análise.

    O estimador salva os nomes:
        potencia_estimada_kW
        erro_percentual
        R_kW

    A potência real pode estar na coluna 'potencia_real_kW'.
    """

    # Compatibilidade caso alguma versão antiga tenha usado
    # nomes com letras maiúsculas.
    renomear = {}

    mapa = {
        "Potencia_real_kW":
            "potencia_real_kW",

        "Potencia_estimada_kW":
            "potencia_estimada_kW",

        "Erro_percentual":
            "erro_percentual",

        "C_eff":
            "C_eff",
    }

    for antigo, novo in mapa.items():

        if (
            antigo in todos.columns
            and novo not in todos.columns
        ):
            renomear[antigo] = novo

    if renomear:
        todos = todos.rename(
            columns=renomear
        )

    # Caso a potência real não tenha sido gravada
    # na planilha, ela pode ser recuperada da relação
    # conhecida dos cenários.
    if "potencia_real_kW" not in todos.columns:

        potencias = {
            "20": 294.62,
            "40": 589.24,
            "60": 883.86,
        }

        if "Cenario" in todos.columns:

            def obter_potencia_real(valor):

                texto = str(valor).replace(
                    "_VV",
                    ""
                )

                return potencias.get(
                    texto,
                    float("nan")
                )

            todos["potencia_real_kW"] = (
                todos["Cenario"]
                .apply(obter_potencia_real)
            )

    return todos


# ============================================================================
# ESTATÍSTICAS
# ============================================================================

def calcular_estatisticas(todos):

    print_header(
        "CALCULANDO ESTATÍSTICAS"
    )

    grupos = [
        "Cenario",
        "Janela",
        "VoltVar",
    ]

    obrigatorias = grupos + [
        "potencia_real_kW",
        "potencia_estimada_kW",
        "erro_percentual",
    ]

    faltantes = [
        coluna
        for coluna in obrigatorias
        if coluna not in todos.columns
    ]

    if faltantes:

        print(
            "\nColunas disponíveis na planilha:"
        )

        for coluna in todos.columns:
            print(f"  - {coluna}")

        raise ValueError(
            "\nColunas necessárias não encontradas: "
            + ", ".join(faltantes)
        )

    # ------------------------------------------------------------------------
    # Estatísticas principais
    # ------------------------------------------------------------------------

    agregacoes = {
        "Execucao": "nunique",

        "potencia_real_kW":
            "mean",

        "potencia_estimada_kW":
            [
                "mean",
                "std",
                "min",
                "max",
            ],

        "erro_percentual":
            [
                "mean",
                "std",
                "min",
                "max",
            ],
    }

    # Métricas adicionais do ajuste.
    if "R2" in todos.columns:

        agregacoes["R2"] = [
            "mean",
            "std",
            "min",
            "max",
        ]

    if "k_eff" in todos.columns:

        agregacoes["k_eff"] = [
            "mean",
            "std",
            "min",
            "max",
        ]

    if "C_eff" in todos.columns:

        agregacoes["C_eff"] = [
            "mean",
            "std",
            "min",
            "max",
        ]

    if "R_kW" in todos.columns:

        agregacoes["R_kW"] = [
            "mean",
            "std",
            "min",
            "max",
        ]

    if "RMSE_kW" in todos.columns:

        agregacoes["RMSE_kW"] = [
            "mean",
            "std",
            "min",
            "max",
        ]

    if "MAE_kW" in todos.columns:

        agregacoes["MAE_kW"] = [
            "mean",
            "std",
            "min",
            "max",
        ]

    estat = (
        todos
        .groupby(
            grupos,
            dropna=False
        )
        .agg(agregacoes)
        .reset_index()
    )

    # ------------------------------------------------------------------------
    # Achata MultiIndex das colunas.
    # ------------------------------------------------------------------------

    novas_colunas = []

    for coluna in estat.columns:

        if not isinstance(
            coluna,
            tuple
        ):

            novas_colunas.append(
                str(coluna)
            )

            continue

        base, funcao = coluna

        if base == "Execucao":

            novas_colunas.append(
                "Numero_execucoes"
            )

        elif base == "potencia_real_kW":

            novas_colunas.append(
                "Potencia_real_kW"
            )

        elif base == "potencia_estimada_kW":

            novas_colunas.append(
                f"Potencia_estimada_{funcao}_kW"
            )

        elif base == "erro_percentual":

            novas_colunas.append(
                f"Erro_{funcao}_percentual"
            )

        elif base == "R2":

            novas_colunas.append(
                f"R2_{funcao}"
            )

        elif base == "k_eff":

            novas_colunas.append(
                f"k_eff_{funcao}"
            )

        elif base == "C_eff":

            novas_colunas.append(
                f"C_eff_{funcao}_kW"
            )

        elif base == "R_kW":

            novas_colunas.append(
                f"R_{funcao}_kW"
            )

        elif base == "RMSE_kW":

            novas_colunas.append(
                f"RMSE_{funcao}_kW"
            )

        elif base == "MAE_kW":

            novas_colunas.append(
                f"MAE_{funcao}_kW"
            )

        else:

            novas_colunas.append(
                "_".join(
                    str(x)
                    for x in coluna
                    if str(x) != ""
                )
            )

    estat.columns = novas_colunas

    # ------------------------------------------------------------------------
    # Erro absoluto médio
    # ------------------------------------------------------------------------

    erro_absoluto = (
        todos
        .groupby(
            grupos,
            dropna=False
        )["erro_percentual"]
        .apply(
            lambda serie:
            serie.abs().mean()
        )
        .reset_index(
            name="Erro_absoluto_medio_percentual"
        )
    )

    estat = estat.merge(
        erro_absoluto,
        on=grupos,
        how="left"
    )

    return estat


# ============================================================================
# ESTATÍSTICAS POR EXECUÇÃO
# ============================================================================

def calcular_resultados_por_execucao(todos):

    colunas = [
        "Execucao",
        "Cenario",
        "Janela",
        "VoltVar",
        "potencia_real_kW",
        "potencia_estimada_kW",
        "erro_percentual",
    ]

    disponiveis = [
        coluna
        for coluna in colunas
        if coluna in todos.columns
    ]

    return todos[disponiveis].copy()


# ============================================================================
# GRÁFICO — REAL X ESTIMADA
# ============================================================================

def gerar_grafico_real_vs_estimado(todos):

    figura, eixo = plt.subplots(
        figsize=(10, 8)
    )

    for valor, rotulo in [
        (False, "FP=1"),
        (True, "Volt-VAr"),
    ]:

        dados = todos[
            todos["VoltVar"] == valor
        ]

        if dados.empty:
            continue

        eixo.scatter(
            dados["potencia_real_kW"],
            dados["potencia_estimada_kW"],
            label=rotulo,
            alpha=0.65,
            s=45,
        )

    valores = pd.concat(
        [
            todos["potencia_real_kW"],
            todos["potencia_estimada_kW"],
        ]
    ).dropna()

    if not valores.empty:

        minimo = valores.min()
        maximo = valores.max()

        margem = (
            (maximo - minimo) * 0.05
        )

        if margem == 0:
            margem = 1

        eixo.plot(
            [
                minimo - margem,
                maximo + margem,
            ],
            [
                minimo - margem,
                maximo + margem,
            ],
            linestyle="--",
            label="Estimação perfeita (y=x)",
        )

    eixo.set_xlabel(
        "Potência PV real instalada (kW)"
    )

    eixo.set_ylabel(
        "Potência PV estimada pelo modelo de Kara (kW)"
    )

    eixo.set_title(
        "Kara + PVWatts — 10 execuções\n"
        "Potência real × potência estimada"
    )

    eixo.grid(
        True,
        alpha=0.3
    )

    eixo.legend()

    figura.tight_layout()

    arquivo = (
        PASTA_ANALISE
        / "Potencia_Real_vs_Estimada_10_Execucoes.png"
    )

    figura.savefig(
        arquivo,
        dpi=300,
        bbox_inches="tight"
    )

    plt.close(figura)

    return arquivo


# ============================================================================
# GRÁFICO — ERRO
# ============================================================================

def gerar_grafico_erros(todos):

    dados = todos.copy()

    dados["Ambiente"] = (
        dados["VoltVar"]
        .map(
            {
                False: "FP=1",
                True: "Volt-VAr",
            }
        )
    )

    dados["Grupo"] = (
        dados["Cenario"].astype(str)
        + " - "
        + dados["Janela"].astype(str)
        + " - "
        + dados["Ambiente"]
    )

    figura, eixo = plt.subplots(
        figsize=(15, 8)
    )

    dados.boxplot(
        column="erro_percentual",
        by="Grupo",
        ax=eixo,
        rot=75
    )

    figura.suptitle("")

    eixo.set_title(
        "Distribuição do erro — 10 execuções"
    )

    eixo.set_xlabel(
        "Cenário - janela - ambiente"
    )

    eixo.set_ylabel(
        "Erro (%)"
    )

    eixo.grid(
        True,
        alpha=0.3
    )

    figura.tight_layout()

    arquivo = (
        PASTA_ANALISE
        / "Erro_por_Execucao.png"
    )

    figura.savefig(
        arquivo,
        dpi=300,
        bbox_inches="tight"
    )

    plt.close(figura)

    return arquivo


# ============================================================================
# SALVAMENTO
# ============================================================================

def salvar_resultados(
    todos,
    estatisticas,
    resultados_execucao,
    status
):

    PASTA_ANALISE.mkdir(
        parents=True,
        exist_ok=True
    )

    arquivo_todos = (
        PASTA_ANALISE
        / "Resultados_Kara_PVWatts_todas_execucoes.xlsx"
    )

    arquivo_estatisticas = (
        PASTA_ANALISE
        / "Estatisticas_Kara_PVWatts.xlsx"
    )

    arquivo_csv = (
        PASTA_ANALISE
        / "Estatisticas_Kara_PVWatts.csv"
    )

    arquivo_txt = (
        PASTA_ANALISE
        / "Resumo_Kara_PVWatts.txt"
    )

    # ------------------------------------------------------------------------
    # Todos os resultados
    # ------------------------------------------------------------------------

    todos.to_excel(
        arquivo_todos,
        index=False
    )

    # ------------------------------------------------------------------------
    # Estatísticas
    # ------------------------------------------------------------------------

    estatisticas.to_excel(
        arquivo_estatisticas,
        index=False
    )

    estatisticas.to_csv(
        arquivo_csv,
        index=False
    )

    # ------------------------------------------------------------------------
    # Relatório textual
    # ------------------------------------------------------------------------

    sucessos = sum(
        1
        for _, situacao in status
        if situacao == "SUCCESS"
    )

    with arquivo_txt.open(
        "w",
        encoding="utf-8"
    ) as arquivo:

        arquivo.write(
            "KARA + PVWATTS — "
            "ANÁLISE DAS 10 EXECUÇÕES\n"
        )

        arquivo.write(
            "=" * 78
            + "\n\n"
        )

        arquivo.write(
            f"Execuções solicitadas: "
            f"{N_EXECUCOES}\n"
        )

        arquivo.write(
            f"Execuções com resultados: "
            f"{sucessos}\n"
        )

        arquivo.write(
            f"Linhas analisadas: "
            f"{len(todos)}\n\n"
        )

        arquivo.write(
            "STATUS DAS EXECUÇÕES\n"
        )

        arquivo.write(
            "-" * 78
            + "\n"
        )

        for numero, situacao in status:

            arquivo.write(
                f"Execução {numero:02d}: "
                f"{situacao}\n"
            )

        arquivo.write(
            "\nESTATÍSTICAS AGRUPADAS\n"
        )

        arquivo.write(
            "-" * 78
            + "\n\n"
        )

        arquivo.write(
            estatisticas.to_string(
                index=False
            )
        )

        arquivo.write("\n")

    return (
        arquivo_todos,
        arquivo_estatisticas,
        arquivo_csv,
        arquivo_txt,
    )


# ============================================================================
# MAIN
# ============================================================================

def main():

    print_header(
        "KARA + PVWATTS — "
        "ANÁLISE DE 10 EXECUÇÕES"
    )

    print(
        "Pasta dos experimentos:"
    )

    print(
        f"  {EXPERIMENT_ROOT}"
    )

    print(
        "\nPasta da análise:"
    )

    print(
        f"  {PASTA_ANALISE}"
    )

    # ------------------------------------------------------------------------
    # 1. Coleta
    # ------------------------------------------------------------------------

    todos, status = (
        coletar_resultados()
    )

    # ------------------------------------------------------------------------
    # 2. Ajuste dos nomes/identificação da potência real
    # ------------------------------------------------------------------------

    todos = preparar_colunas(
        todos
    )

    # ------------------------------------------------------------------------
    # 3. Estatísticas
    # ------------------------------------------------------------------------

    estatisticas = (
        calcular_estatisticas(
            todos
        )
    )

    resultados_execucao = (
        calcular_resultados_por_execucao(
            todos
        )
    )

    # ------------------------------------------------------------------------
    # 4. Salva tabelas
    # ------------------------------------------------------------------------

    arquivos = salvar_resultados(
        todos,
        estatisticas,
        resultados_execucao,
        status
    )

    # ------------------------------------------------------------------------
    # 5. Gráficos
    # ------------------------------------------------------------------------

    grafico_real = (
        gerar_grafico_real_vs_estimado(
            todos
        )
    )

    grafico_erro = (
        gerar_grafico_erros(
            todos
        )
    )

    # ------------------------------------------------------------------------
    # 6. Console
    # ------------------------------------------------------------------------

    print_header(
        "RESULTADO DA ANÁLISE"
    )

    print(
        f"Execuções coletadas: "
        f"{todos['Execucao'].nunique()}"
    )

    print(
        f"Resultados individuais: "
        f"{len(todos)}"
    )

    print(
        "\nArquivos gerados:"
    )

    for arquivo in arquivos:
        print(
            f"  {arquivo}"
        )

    print(
        f"  {grafico_real}"
    )

    print(
        f"  {grafico_erro}"
    )

    print(
        "\nMÉDIAS POR CENÁRIO / JANELA / AMBIENTE:"
    )

    colunas_resumo = [
        "Cenario",
        "Janela",
        "VoltVar",
        "Numero_execucoes",
        "Erro_mean_percentual",
        "Erro_std_percentual",
        "Erro_absoluto_medio_percentual",
        "Potencia_estimada_mean_kW",
        "Potencia_estimada_std_kW",
    ]

    disponiveis = [
        coluna
        for coluna in colunas_resumo
        if coluna in estatisticas.columns
    ]

    print(
        estatisticas[
            disponiveis
        ].to_string(
            index=False
        )
    )

    print_header(
        "CONCLUÍDO"
    )


if __name__ == "__main__":
    main()
