# -*- coding: utf-8 -*-

from pathlib import Path
from itertools import combinations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# =============================================================================
# CONFIGURAÇÃO
# =============================================================================

ARQUIVO = Path(
    "/home/matheus/Documentos/BtM-PV-estimating_BKP_3/"
    "BtM-PV-estimating_A1_VoltVar/"
    "dados/outputs/carga_base/"
    "resultados_sem_PV.parquet"
)

PASTA_SAIDA = (
    ARQUIVO.parent /
    "analise_linearidade_deltaP_deltaQ_sem_PV"
)


# =============================================================================
# LEITURA DOS DADOS
# =============================================================================

def carregar_dados():

    if not ARQUIVO.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado:\n{ARQUIVO}"
        )

    df = pd.read_parquet(ARQUIVO)

    print(f"Arquivo: {ARQUIVO}")
    print(f"Linhas: {len(df)}")
    print(f"Colunas: {df.columns.tolist()}")

    # -------------------------------------------------------------------------
    # O arquivo sem PV possui 8760 registros e NÃO possui coluna "dia".
    #
    # Portanto, o dia é reconstruído pela posição dos registros.
    # Cada dia possui 24 registros.
    # -------------------------------------------------------------------------

    if len(df) % 24 != 0:
        raise ValueError(
            f"O arquivo possui {len(df)} linhas, "
            "que não é múltiplo de 24. "
            "Não é possível reconstruir os dias automaticamente."
        )

    n_dias = len(df) // 24

    df = df.copy()

    # Reinicia o índice para garantir que a posição corresponda
    # à sequência temporal do arquivo.
    df = df.reset_index(drop=True)

    df["dia"] = np.repeat(
        np.arange(1, n_dias + 1),
        24
    )

    # A coluna hora já existe no arquivo.
    # Não precisamos recriá-la.

    colunas = {"dia", "hora", "P_kW", "Q_kvar"}

    faltantes = colunas - set(df.columns)

    if faltantes:
        raise ValueError(
            f"Colunas necessárias ausentes: {sorted(faltantes)}\n"
            f"Colunas disponíveis: {df.columns.tolist()}"
        )

    print(f"Dias reconstruídos: {n_dias}")

    return df


# =============================================================================
# CÁLCULO DE ΔP_L E ΔQ_L
# =============================================================================

def calcular_deltas(df):
    """
    Forma todos os pares de dias usando a posição temporal dos dados.

    O arquivo possui 8760 registros consecutivos. Como a coluna 'hora'
    pode representar o índice horário anual (0...8759), não usamos a coluna
    'hora' para fazer o merge entre dias.

    Os dados são reorganizados como:
        dias × 24 horas

    e cada par de dias é comparado na mesma hora do dia.
    """

    dados = df[
        ["dia", "P_kW", "Q_kvar"]
    ].copy()

    dados = dados.dropna(
        subset=["P_kW", "Q_kvar"]
    )

    # Para esta análise precisamos manter exatamente 24 registros por dia.
    contagem_por_dia = dados.groupby("dia").size()

    if not np.all(contagem_por_dia.to_numpy() == 24):
        raise ValueError(
            "Nem todos os dias possuem exatamente 24 observações."
        )

    dias = sorted(dados["dia"].unique())

    # Matriz: linhas = dias; colunas = horas do dia.
    P = (
        dados
        .sort_values(["dia"])
        ["P_kW"]
        .to_numpy(dtype=float)
        .reshape(len(dias), 24)
    )

    Q = (
        dados
        .sort_values(["dia"])
        ["Q_kvar"]
        .to_numpy(dtype=float)
        .reshape(len(dias), 24)
    )

    resultados = []

    # Todos os pares de dias.
    for i, j in combinations(range(len(dias)), 2):

        delta_p = P[j] - P[i]
        delta_q = Q[j] - Q[i]

        resultados.append(
            pd.DataFrame({
                "dia_1": dias[i],
                "dia_2": dias[j],
                "hora": np.arange(24),
                "deltaP": delta_p,
                "deltaQ": delta_q,
            })
        )

    return pd.concat(
        resultados,
        ignore_index=True
    )


# =============================================================================
# AJUSTE ΔP_L = α ΔQ_L
# =============================================================================

def ajustar_modelo(delta_df):

    x = delta_df["deltaQ"].to_numpy(
        dtype=float
    )

    y = delta_df["deltaP"].to_numpy(
        dtype=float
    )

    mascara = (
        np.isfinite(x) &
        np.isfinite(y)
    )

    x = x[mascara]
    y = y[mascara]

    if len(x) < 2:
        raise ValueError(
            "Número insuficiente de observações."
        )

    soma_x2 = np.sum(x ** 2)

    if np.isclose(soma_x2, 0):
        raise ValueError(
            "A variação de Q é praticamente nula."
        )

    # Regressão pela origem:
    #
    #     ΔP_L = α ΔQ_L
    #
    alpha = np.sum(x * y) / soma_x2

    y_hat = alpha * x

    residuos = y - y_hat

    sse = np.sum(residuos ** 2)

    # R² para regressão pela origem.
    sst_origem = np.sum(y ** 2)

    r2 = (
        1 - sse / sst_origem
        if not np.isclose(sst_origem, 0)
        else np.nan
    )

    rmse = np.sqrt(
        np.mean(residuos ** 2)
    )

    if (
        np.std(x) > 0 and
        np.std(y) > 0
    ):
        pearson = np.corrcoef(
            x, y
        )[0, 1]
    else:
        pearson = np.nan

    return {
        "alpha": alpha,
        "r2": r2,
        "pearson": pearson,
        "rmse": rmse,
        "n": len(x),
        "sse": sse,
    }


# =============================================================================
# GRÁFICO
# =============================================================================
def gerar_grafico(delta_df, resultado):

    x = delta_df["deltaQ"].to_numpy(
        dtype=float
    )

    y = delta_df["deltaP"].to_numpy(
        dtype=float
    )

    alpha = resultado["alpha"]

    limite = max(
        np.max(np.abs(x)),
        np.max(np.abs(y))
    )

    if limite <= 0:
        limite = 1.0

    xx = np.linspace(
        -limite,
        limite,
        300
    )

    fig, ax = plt.subplots(
        figsize=(9, 7)
    )

    ax.scatter(
        x,
        y,
        s=4,
        alpha=0.12,
        rasterized=True
    )

    ax.plot(
        xx,
        alpha * xx,
        linewidth=2,
        label=(
            rf"$\Delta P_L = "
            rf"{alpha:.4f}\Delta Q_L$"
        )
    )

    ax.axhline(
        0,
        linewidth=0.7
    )

    ax.axvline(
        0,
        linewidth=0.7
    )

    ax.set_xlabel(
        r"$\Delta Q_L$ (kvar)"
    )

    ax.set_ylabel(
        r"$\Delta P_L$ (kW)"
    )

    ax.set_title(
        r"Relationship between $\Delta P_L$ and $\Delta Q_L$"
        "\nSimulation without PV"
    )

    texto = (
        rf"$\alpha={alpha:.4f}$" "\n"
        rf"$R^2={resultado['r2']:.4f}$" "\n"
        rf"$r={resultado['pearson']:.4f}$" "\n"
        rf"$RMSE={resultado['rmse']:.3f}$ kW"
    )

    ax.text(
        0.03,
        0.97,
        texto,
        transform=ax.transAxes,
        va="top",
        bbox=dict(
            boxstyle="round",
            alpha=0.85
        )
    )

    ax.grid(
        True,
        alpha=0.25
    )

    ax.legend()

    fig.tight_layout()

    caminho = (
        PASTA_SAIDA /
        "linearidade_deltaP_deltaQ_sem_PV.png"
    )

    fig.savefig(
        caminho,
        dpi=300,
        bbox_inches="tight"
    )

    plt.close(fig)

    return caminho
# =============================================================================
# MAIN
# =============================================================================

def main():

    print("=" * 80)
    print("TESTE DA LINEARIDADE ENTRE ΔP_L E ΔQ_L")
    print("SIMULAÇÃO SEM PV")
    print("=" * 80)

    PASTA_SAIDA.mkdir(
        parents=True,
        exist_ok=True
    )

    # 1. Lê e prepara os dados
    df = carregar_dados()

    # 2. Forma todos os pares de dias
    delta_df = calcular_deltas(df)

    n_dias = df["dia"].nunique()

    n_pares = (
        delta_df[
            ["dia_1", "dia_2"]
        ]
        .drop_duplicates()
        .shape[0]
    )

    print()
    print(f"Dias:                    {n_dias}")
    print(f"Pares de dias:           {n_pares}")
    print(f"Observações ΔP/ΔQ:       {len(delta_df)}")

    # 3. Ajusta ΔP_L = α ΔQ_L
    resultado = ajustar_modelo(
        delta_df
    )

    print()
    print("-" * 80)
    print("RESULTADO")
    print("-" * 80)
    print(
        f"alpha:                   "
        f"{resultado['alpha']:.6f}"
    )
    print(
        f"R² pela origem:          "
        f"{resultado['r2']:.6f}"
    )
    print(
        f"Pearson r:               "
        f"{resultado['pearson']:.6f}"
    )
    print(
        f"RMSE:                    "
        f"{resultado['rmse']:.6f} kW"
    )

    # 4. Gráfico
    caminho_grafico = gerar_grafico(
        delta_df,
        resultado
    )

    # 5. Salva resumo
    resumo = pd.DataFrame([{
        "arquivo": ARQUIVO.name,
        "dias": n_dias,
        "pares_dias": n_pares,
        "observacoes": resultado["n"],
        "alpha": resultado["alpha"],
        "R2_origem": resultado["r2"],
        "Pearson_r": resultado["pearson"],
        "RMSE_kW": resultado["rmse"],
        "SSE": resultado["sse"],
    }])

    caminho_excel = (
        PASTA_SAIDA /
        "resultado_linearidade_sem_PV.xlsx"
    )

    resumo.to_excel(
        caminho_excel,
        index=False
    )

    print()
    print("=" * 80)
    print("CONCLUÍDO")
    print("=" * 80)
    print(f"Gráfico: {caminho_grafico}")
    print(f"Excel:   {caminho_excel}")


if __name__ == "__main__":
    main()
