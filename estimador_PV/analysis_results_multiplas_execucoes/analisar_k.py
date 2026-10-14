import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

# ============================================================
# CONFIGURATION
# ============================================================

ARQUIVO = Path("Multiple_Executions_Final_Analysis.xlsx")
ABA = "Final_Results"
ARQUIVO_SAIDA = Path("Analise_resultados_por_cenario_PV.xlsx")
DIRETORIO_GRAFICOS = Path("graficos_analise_k")


# ============================================================
# LOAD DATA
# ============================================================

df = pd.read_excel(ARQUIVO, sheet_name=ABA)
df.columns = [str(c).strip() for c in df.columns]

required_columns = ["k", "Condition", "Cenário", "Erro (%)"]
missing = [column for column in required_columns if column not in df.columns]

if missing:
    raise ValueError(
        f"Required columns not found: {missing}\n"
        f"Available columns: {list(df.columns)}"
    )

for column in ["k", "Cenário", "Erro (%)"]:
    df[column] = pd.to_numeric(df[column], errors="coerce")

df["Condition"] = df["Condition"].astype(str).str.strip()
df = df.dropna(subset=required_columns).copy()

if df.empty:
    raise ValueError("No valid records found after converting the required columns.")

# Keep penetration scenarios in numeric order (e.g., 20%, 40%, 60%).
scenarios = sorted(df["Cenário"].unique())
conditions = sorted(df["Condition"].unique())


# ============================================================
# SUMMARY BY PV PENETRATION SCENARIO, INVERTER CONDITION AND k
# ============================================================

resumo = (
    df.groupby(["Cenário", "Condition", "k"], as_index=False)
      .agg(
          Erro_medio_pct=("Erro (%)", "mean"),
          Erro_mediano_pct=("Erro (%)", "median"),
          Desvio_padrao_pct=("Erro (%)", "std"),
          Erro_minimo_pct=("Erro (%)", "min"),
          Erro_maximo_pct=("Erro (%)", "max"),
          N=("Erro (%)", "count"),
      )
      .sort_values(["Cenário", "Condition", "k"])
)

# Standard deviation is undefined when there is only one observation.
resumo["Desvio_padrao_pct"] = resumo["Desvio_padrao_pct"].fillna(0)


# ============================================================
# PRINT DETAILED RESULTS FOR EACH PENETRATION SCENARIO
# ============================================================

print("\\n" + "=" * 110)
print("ERROR ANALYSIS BY PV PENETRATION SCENARIO")
print("=" * 110)

for scenario in scenarios:
    print(f"\\nPV PENETRATION SCENARIO: {scenario:g}%")
    print("-" * 110)

    scenario_data = resumo[resumo["Cenário"] == scenario]

    for condition in conditions:
        condition_data = scenario_data[scenario_data["Condition"] == condition]

        if condition_data.empty:
            continue

        print(f"\\nInverter condition: {condition}")
        print(
            condition_data[
                [
                    "k",
                    "Erro_medio_pct",
                    "Erro_mediano_pct",
                    "Desvio_padrao_pct",
                    "Erro_minimo_pct",
                    "Erro_maximo_pct",
                    "N",
                ]
            ].to_string(
                index=False,
                formatters={
                    "k": "{:.3f}".format,
                    "Erro_medio_pct": "{:.3f}".format,
                    "Erro_mediano_pct": "{:.3f}".format,
                    "Desvio_padrao_pct": "{:.3f}".format,
                    "Erro_minimo_pct": "{:.3f}".format,
                    "Erro_maximo_pct": "{:.3f}".format,
                },
            )
        )

        best = condition_data.loc[condition_data["Erro_medio_pct"].idxmin()]
        print(
            f"Best k for this scenario and condition: {best['k']:.3f} "
            f"(mean error = {best['Erro_medio_pct']:.3f}%, "
            f"standard deviation = {best['Desvio_padrao_pct']:.3f}%, "
            f"N = {int(best['N'])})"
        )


# ============================================================
# BEST k FOR EACH SCENARIO AND INVERTER CONDITION
# ============================================================

idx_best = resumo.groupby(["Cenário", "Condition"])["Erro_medio_pct"].idxmin()
melhores = (
    resumo.loc[idx_best]
          .sort_values(["Cenário", "Condition"])
          .reset_index(drop=True)
)

print("\\n" + "=" * 110)
print("BEST k BY PV PENETRATION SCENARIO AND INVERTER CONDITION")
print("=" * 110)
print(
    melhores[
        [
            "Cenário",
            "Condition",
            "k",
            "Erro_medio_pct",
            "Desvio_padrao_pct",
            "Erro_minimo_pct",
            "Erro_maximo_pct",
            "N",
        ]
    ].to_string(
        index=False,
        formatters={
            "Cenário": "{:g}".format,
            "k": "{:.3f}".format,
            "Erro_medio_pct": "{:.3f}".format,
            "Desvio_padrao_pct": "{:.3f}".format,
            "Erro_minimo_pct": "{:.3f}".format,
            "Erro_maximo_pct": "{:.3f}".format,
        },
    )
)


# ============================================================
# OVERALL SUMMARY BY SCENARIO AND CONDITION
# Average is calculated across all k values and executions.
# This is descriptive; it is not used to select the best k.
# ============================================================

resumo_geral = (
    df.groupby(["Cenário", "Condition"], as_index=False)
      .agg(
          Erro_medio_pct=("Erro (%)", "mean"),
          Desvio_padrao_pct=("Erro (%)", "std"),
          Erro_minimo_pct=("Erro (%)", "min"),
          Erro_maximo_pct=("Erro (%)", "max"),
          N=("Erro (%)", "count"),
      )
      .sort_values(["Cenário", "Condition"])
)
resumo_geral["Desvio_padrao_pct"] = resumo_geral["Desvio_padrao_pct"].fillna(0)

print("\\n" + "=" * 110)
print("OVERALL SUMMARY BY PV PENETRATION SCENARIO AND INVERTER CONDITION")
print("=" * 110)
print(
    resumo_geral.to_string(
        index=False,
        formatters={
            "Cenário": "{:g}".format,
            "Erro_medio_pct": "{:.3f}".format,
            "Desvio_padrao_pct": "{:.3f}".format,
            "Erro_minimo_pct": "{:.3f}".format,
            "Erro_maximo_pct": "{:.3f}".format,
        },
    )
)


# ============================================================
# EXPORT TABLES TO EXCEL
# ============================================================

with pd.ExcelWriter(ARQUIVO_SAIDA, engine="openpyxl") as writer:
    df.sort_values(["Cenário", "Condition", "k"]).to_excel(
        writer, sheet_name="Raw_Results", index=False
    )
    resumo.to_excel(writer, sheet_name="Summary_by_Scenario_k", index=False)
    melhores.to_excel(writer, sheet_name="Best_k_by_Scenario", index=False)
    resumo_geral.to_excel(writer, sheet_name="Overall_by_Scenario", index=False)

print("\\n" + "=" * 110)
print(f"Analysis complete. Excel report saved to: {ARQUIVO_SAIDA.resolve()}")
print("Note: the overall summary averages results across all k values;")
print("use 'Best_k_by_Scenario' to compare the best k separately for each scenario.")


# ============================================================
# PLOT: ALL PV PENETRATION SCENARIOS IN ONE FIGURE
# ============================================================

DIRETORIO_GRAFICOS.mkdir(parents=True, exist_ok=True)

fig, ax = plt.subplots(figsize=(10, 6))

# One curve for each scenario and inverter condition (six curves total).
for scenario in scenarios:
    dados_cenario = resumo[resumo["Cenário"] == scenario]

    for condition in conditions:
        dados_condicao = (
            dados_cenario[dados_cenario["Condition"] == condition]
            .sort_values("k")
        )

        if dados_condicao.empty:
            continue

        ax.plot(
            dados_condicao["k"],
            dados_condicao["Erro_medio_pct"],
            marker="o",
            linewidth=2,
            markersize=5,
            label=f"{scenario:g}% - {condition}",
        )

ax.set_title("Mean PV capacity estimation error vs. parameter k")
ax.set_xlabel("Parameter k")
ax.set_ylabel("Mean estimation error (%)")
ax.set_xticks(sorted(df["k"].unique()))
ax.grid(True, linestyle="--", alpha=0.5)
ax.legend(title="PV penetration - inverter condition", ncol=2)
fig.tight_layout()

arquivo_grafico = DIRETORIO_GRAFICOS / "erro_medio_k_todos_cenarios.png"
fig.savefig(arquivo_grafico, dpi=300, bbox_inches="tight")
print(f"Combined plot saved: {arquivo_grafico.resolve()}")

plt.show()
plt.close(fig)

print(f"Plot saved in: {DIRETORIO_GRAFICOS.resolve()}")
