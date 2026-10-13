# -*- coding: utf-8 -*-
"""
Análise da linearidade entre ΔP_L e ΔQ

Objetivo
--------
Verificar empiricamente, dentro de cada cluster, a relação:

    ΔP_L(t) ≈ α ΔQ(t)

Os arquivos dos clusters possuem as colunas:
    hora
    P_kW
    Q_kvar
    dia

Para cada cenário e cluster:
1. São formados todos os pares possíveis de dias.
2. Para cada par são calculados ΔP e ΔQ.
3. Todos os pares são concatenados.
4. É ajustada uma reta passando pela origem:
       ΔP = α ΔQ
5. São calculados:
       α
       R² (ajuste pela origem)
       correlação de Pearson
       RMSE
       número de observações
6. São gerados gráficos individuais por cluster e gráficos consolidados
   por cenário.

Não é utilizado P_PV para construir ΔP ou ΔQ.
"""

from pathlib import Path
from itertools import combinations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from localizar_clusters import localizar_clusters


# =============================================================================
# CONFIGURAÇÕES
# =============================================================================

TIPO = "FP1"                  # "FP1" ou "VV"
CENARIOS = (20, 40, 60)

COL_DIA = "dia"
COL_HORA = "hora"
COL_P = "P_kW"
COL_Q = "Q_kvar"

NOME_SAIDA = "analise_linearidade_deltaP_deltaQ"


# =============================================================================
# FUNÇÕES
# =============================================================================

def calcular_deltas_todos_os_pares(df):
    """
    Calcula ΔP e ΔQ para todos os pares de dias do cluster.

    Convenção:
        ΔP = P_d2 - P_d1
        ΔQ = Q_d2 - Q_d1

    Retorna um DataFrame com:
        dia_1, dia_2, hora, deltaP, deltaQ
    """

    colunas_necessarias = {COL_DIA, COL_HORA, COL_P, COL_Q}

    faltantes = colunas_necessarias - set(df.columns)
    if faltantes:
        raise ValueError(
            f"Colunas ausentes: {sorted(faltantes)}"
        )

    dados = df[[COL_DIA, COL_HORA, COL_P, COL_Q]].copy()

    dados = dados.dropna(
        subset=[COL_DIA, COL_HORA, COL_P, COL_Q]
    )

    # Ordenação para garantir consistência temporal.
    dados = dados.sort_values([COL_DIA, COL_HORA])

    dias = sorted(dados[COL_DIA].unique())

    pares = []

    for dia_1, dia_2 in combinations(dias, 2):

        d1 = dados[dados[COL_DIA] == dia_1][
            [COL_HORA, COL_P, COL_Q]
        ].copy()

        d2 = dados[dados[COL_DIA] == dia_2][
            [COL_HORA, COL_P, COL_Q]
        ].copy()

        # Junta os dois dias pela hora.
        par = pd.merge(
            d1,
            d2,
            on=COL_HORA,
            how="inner",
            suffixes=("_d1", "_d2")
        )

        if par.empty:
            continue

        par["dia_1"] = dia_1
        par["dia_2"] = dia_2

        par["deltaP"] = (
            par[f"{COL_P}_d2"] -
            par[f"{COL_P}_d1"]
        )

        par["deltaQ"] = (
            par[f"{COL_Q}_d2"] -
            par[f"{COL_Q}_d1"]
        )

        pares.append(
            par[
                [
                    "dia_1",
                    "dia_2",
                    COL_HORA,
                    "deltaP",
                    "deltaQ"
                ]
            ]
        )

    if not pares:
        return pd.DataFrame(
            columns=[
                "dia_1",
                "dia_2",
                COL_HORA,
                "deltaP",
                "deltaQ"
            ]
        )

    return pd.concat(pares, ignore_index=True)


def ajustar_reta_origem(delta_q, delta_p):
    """
    Ajusta:

        ΔP = α ΔQ

    pelo método dos mínimos quadrados, impondo intercepto zero.
    """

    x = np.asarray(delta_q, dtype=float)
    y = np.asarray(delta_p, dtype=float)

    mascara = np.isfinite(x) & np.isfinite(y)
    x = x[mascara]
    y = y[mascara]

    if len(x) < 2:
        raise ValueError("Número insuficiente de observações.")

    soma_x2 = np.sum(x ** 2)

    if np.isclose(soma_x2, 0):
        raise ValueError(
            "ΔQ possui variância/energia praticamente nula."
        )

    alpha = np.sum(x * y) / soma_x2

    y_pred = alpha * x
    residuos = y - y_pred

    sse = np.sum(residuos ** 2)
    sst_origem = np.sum(y ** 2)

    if np.isclose(sst_origem, 0):
        r2 = np.nan
    else:
        r2 = 1.0 - sse / sst_origem

    rmse = np.sqrt(np.mean(residuos ** 2))

    if len(x) >= 2 and np.std(x) > 0 and np.std(y) > 0:
        correlacao = np.corrcoef(x, y)[0, 1]
    else:
        correlacao = np.nan

    return {
        "alpha": alpha,
        "r2_origem": r2,
        "correlacao_pearson": correlacao,
        "rmse": rmse,
        "n_observacoes": len(x),
        "sse": sse,
    }


def criar_grafico_cluster(
    delta_df,
    resultado,
    cenario,
    cluster,
    pasta_saida
):
    """Cria gráfico ΔQ × ΔP para um cluster."""

    x = delta_df["deltaQ"].to_numpy(dtype=float)
    y = delta_df["deltaP"].to_numpy(dtype=float)

    alpha = resultado["alpha"]

    fig, ax = plt.subplots(figsize=(8, 6))

    ax.scatter(
        x,
        y,
        s=7,
        alpha=0.20,
        rasterized=True
    )

    limite = max(
        np.max(np.abs(x)),
        np.max(np.abs(y))
    )

    if limite == 0:
        limite = 1.0

    xx = np.linspace(-limite, limite, 300)
    yy = alpha * xx

    ax.plot(
        xx,
        yy,
        linewidth=2,
        label=rf"$\Delta P_L = {alpha:.4f}\Delta Q$"
    )

    ax.axhline(0, linewidth=0.7)
    ax.axvline(0, linewidth=0.7)

    ax.set_xlabel(r"$\Delta Q$ (kvar)")
    ax.set_ylabel(r"$\Delta P_L$ (kW)")

    ax.set_title(
        f"Cenário {cenario}% — Cluster {cluster}"
    )

    texto = (
        rf"$\alpha={alpha:.4f}$" "\n"
        rf"$R^2={resultado['r2_origem']:.4f}$" "\n"
        rf"$r={resultado['correlacao_pearson']:.4f}$" "\n"
        rf"$RMSE={resultado['rmse']:.3f}$ kW" "\n"
        rf"$N={resultado['n_observacoes']}$"
    )

    ax.text(
        0.03,
        0.97,
        texto,
        transform=ax.transAxes,
        va="top",
        bbox=dict(boxstyle="round", alpha=0.85)
    )

    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()

    nome = (
        f"linearidade_cenario_{cenario}_"
        f"cluster_{cluster}.png"
    )

    fig.savefig(
        pasta_saida / nome,
        dpi=300,
        bbox_inches="tight"
    )

    plt.close(fig)


def criar_grafico_consolidado(
    resultados_cluster,
    dados_graficos,
    cenario,
    pasta_saida
):
    """
    Cria uma figura consolidada dos quatro clusters.
    """

    fig, axes = plt.subplots(
        2,
        2,
        figsize=(12, 10)
    )

    axes = axes.ravel()

    for idx, cluster in enumerate(sorted(dados_graficos)):

        ax = axes[idx]

        delta_df = dados_graficos[cluster]
        resultado = resultados_cluster[cluster]

        x = delta_df["deltaQ"].to_numpy(dtype=float)
        y = delta_df["deltaP"].to_numpy(dtype=float)

        alpha = resultado["alpha"]

        ax.scatter(
            x,
            y,
            s=5,
            alpha=0.18,
            rasterized=True
        )

        limite = max(
            np.max(np.abs(x)),
            np.max(np.abs(y))
        )

        if limite == 0:
            limite = 1.0

        xx = np.linspace(-limite, limite, 300)

        ax.plot(
            xx,
            alpha * xx,
            linewidth=2
        )

        ax.axhline(0, linewidth=0.6)
        ax.axvline(0, linewidth=0.6)

        ax.set_title(f"Cluster {cluster}")

        ax.set_xlabel(r"$\Delta Q$ (kvar)")
        ax.set_ylabel(r"$\Delta P_L$ (kW)")

        texto = (
            rf"$\alpha={alpha:.4f}$" "\n"
            rf"$R^2={resultado['r2_origem']:.4f}$" "\n"
            rf"$r={resultado['correlacao_pearson']:.4f}$"
        )

        ax.text(
            0.04,
            0.96,
            texto,
            transform=ax.transAxes,
            va="top",
            bbox=dict(boxstyle="round", alpha=0.85)
        )

        ax.grid(True, alpha=0.25)

    fig.suptitle(
        rf"Linearidade entre $\Delta P_L$ e $\Delta Q$ — "
        f"Cenário {cenario}%",
        fontsize=14
    )

    fig.tight_layout()

    nome = (
        f"linearidade_consolidada_cenario_{cenario}.png"
    )

    fig.savefig(
        pasta_saida / nome,
        dpi=300,
        bbox_inches="tight"
    )

    plt.close(fig)


def encontrar_arquivos(estrutura):
    """
    Converte a estrutura retornada por localizar_clusters() em uma
    lista simples de caminhos .parquet.

    localizar_clusters() retorna dicionários em algumas versões do projeto,
    e não necessariamente uma lista de strings.
    """
    encontrados = []

    def percorrer(obj):
        if isinstance(obj, dict):
            for valor in obj.values():
                percorrer(valor)

        elif isinstance(obj, (list, tuple, set)):
            for valor in obj:
                percorrer(valor)

        elif isinstance(obj, (str, Path)):
            caminho = Path(obj)

            if caminho.suffix.lower() == ".parquet":
                encontrados.append(caminho)

    percorrer(estrutura)

    # Remove duplicatas preservando a ordem.
    unicos = []
    vistos = set()

    for caminho in encontrados:
        chave = str(caminho.resolve())

        if chave not in vistos:
            vistos.add(chave)
            unicos.append(caminho)

    return unicos


def encontrar_primeiro_arquivo(estrutura):
    """Retorna o primeiro parquet encontrado."""
    arquivos = encontrar_arquivos(estrutura)

    if not arquivos:
        raise RuntimeError(
            "localizar_clusters() não retornou nenhum arquivo parquet."
        )

    return arquivos[0]


# =============================================================================
# EXECUÇÃO
# =============================================================================

def main():

    print("=" * 80)
    print("ANÁLISE DA LINEARIDADE ENTRE ΔP_L E ΔQ")
    print("=" * 80)
    print(f"Condição: {TIPO}")

    # -------------------------------------------------------------------------
    # Localização dos clusters
    # -------------------------------------------------------------------------

    estrutura_clusters = localizar_clusters(TIPO)
    arquivos = encontrar_arquivos(estrutura_clusters)

    if not arquivos:
        raise RuntimeError(
            f"Nenhum arquivo de cluster encontrado para {TIPO}."
        )

    print(
        f"\nForam localizados {len(arquivos)} arquivos de cluster "
        f"para {TIPO}."
    )

    # -------------------------------------------------------------------------
    # Diretório de saída
    # -------------------------------------------------------------------------

    # Os arquivos dos clusters já estão em:
    # .../dados/outputs/clusters/<TIPO>
    # Assim, não dependemos de configs.py para definir a saída.
    primeiro_arquivo = encontrar_primeiro_arquivo(arquivos)
    pasta_clusters = Path(primeiro_arquivo).resolve().parent

    pasta_saida = (
        pasta_clusters.parent.parent
        / "estimacao_PV"
        / NOME_SAIDA
        / TIPO
    )

    pasta_saida.mkdir(
        parents=True,
        exist_ok=True
    )

    # -------------------------------------------------------------------------
    # Resultados
    # -------------------------------------------------------------------------

    resultados_excel = []

    for cenario in CENARIOS:

        print("\n" + "-" * 80)
        print(f"CENÁRIO {cenario}%")
        print("-" * 80)

        resultados_cluster = {}
        dados_graficos = {}

        for arquivo in arquivos:

            nome = arquivo.name

            # Esperado: Cluster_1_20.parquet
            partes = arquivo.stem.split("_")

            if len(partes) != 3:
                continue

            try:
                cluster = int(partes[1])
                cenario_arquivo = int(partes[2])
            except ValueError:
                continue

            if cenario_arquivo != cenario:
                continue

            print(f"\nCluster {cluster}: {nome}")

            # -----------------------------------------------------------------
            # Leitura
            # -----------------------------------------------------------------

            df = pd.read_parquet(arquivo)

            colunas_necessarias = {
                COL_DIA,
                COL_HORA,
                COL_P,
                COL_Q
            }

            faltantes = (
                colunas_necessarias -
                set(df.columns)
            )

            if faltantes:
                print(
                    "  ERRO: colunas ausentes:",
                    sorted(faltantes)
                )
                continue

            # -----------------------------------------------------------------
            # Deltas
            # -----------------------------------------------------------------

            delta_df = calcular_deltas_todos_os_pares(df)

            if delta_df.empty:
                print(
                    "  ERRO: nenhum par de dias pôde ser formado."
                )
                continue

            print(
                f"  Dias: {df[COL_DIA].nunique()}"
            )

            print(
                f"  Pares de dias: "
                f"{delta_df[['dia_1', 'dia_2']].drop_duplicates().shape[0]}"
            )

            print(
                f"  Observações ΔP/ΔQ: {len(delta_df)}"
            )

            # -----------------------------------------------------------------
            # Ajuste
            # -----------------------------------------------------------------

            try:
                resultado = ajustar_reta_origem(
                    delta_df["deltaQ"],
                    delta_df["deltaP"]
                )
            except ValueError as erro:
                print(f"  ERRO no ajuste: {erro}")
                continue

            resultados_cluster[cluster] = resultado
            dados_graficos[cluster] = delta_df

            print(
                f"  α                 = "
                f"{resultado['alpha']:.6f}"
            )

            print(
                f"  R² (pela origem)   = "
                f"{resultado['r2_origem']:.6f}"
            )

            print(
                f"  Pearson r          = "
                f"{resultado['correlacao_pearson']:.6f}"
            )

            print(
                f"  RMSE               = "
                f"{resultado['rmse']:.6f} kW"
            )

            # -----------------------------------------------------------------
            # Gráfico individual
            # -----------------------------------------------------------------

            criar_grafico_cluster(
                delta_df,
                resultado,
                cenario,
                cluster,
                pasta_saida
            )

            # -----------------------------------------------------------------
            # Resultado para Excel
            # -----------------------------------------------------------------

            resultados_excel.append({
                "Tipo": TIPO,
                "Cenario": cenario,
                "Cluster": cluster,
                "Alpha": resultado["alpha"],
                "R2_origem": resultado["r2_origem"],
                "Pearson_r": resultado["correlacao_pearson"],
                "RMSE_kW": resultado["rmse"],
                "SSE": resultado["sse"],
                "N_observacoes": resultado["n_observacoes"],
                "N_dias": df[COL_DIA].nunique(),
                "N_pares_dias": delta_df[
                    ["dia_1", "dia_2"]
                ].drop_duplicates().shape[0],
            })

        # ---------------------------------------------------------------------
        # Gráfico consolidado
        # ---------------------------------------------------------------------

        if dados_graficos:

            criar_grafico_consolidado(
                resultados_cluster,
                dados_graficos,
                cenario,
                pasta_saida
            )

    # -------------------------------------------------------------------------
    # Excel
    # -------------------------------------------------------------------------

    if resultados_excel:

        df_resultados = pd.DataFrame(
            resultados_excel
        )

        caminho_excel = (
            pasta_saida /
            f"Resultados_linearidade_deltaP_deltaQ_{TIPO}.xlsx"
        )

        df_resultados.to_excel(
            caminho_excel,
            index=False
        )

        print("\n" + "=" * 80)
        print("ANÁLISE CONCLUÍDA")
        print("=" * 80)

        print(
            f"Resultados: {caminho_excel}"
        )

        print(
            f"Gráficos:   {pasta_saida}"
        )

    else:

        print("\nNenhum resultado foi gerado.")


if __name__ == "__main__":
    main()
