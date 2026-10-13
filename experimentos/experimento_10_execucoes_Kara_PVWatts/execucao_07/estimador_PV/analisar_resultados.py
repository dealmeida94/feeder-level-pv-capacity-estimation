#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Analyze PV estimation results.

All analysis outputs are stored in:
    estimador_PV/analysis_results/

Outputs:
    - Excel tables
    - LaTeX table
    - PNG figures
    - TXT summary report

The analysis is entirely in English.
"""

from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt


# ==========================================================
# Paths and settings
# ==========================================================

ROOT = Path(__file__).resolve().parent.parent
ESTIMADOR_DIR = Path(__file__).resolve().parent

# Dedicated folder: keeps generated analysis files separate
# from the Python scripts.
OUTPUT_DIR = ESTIMADOR_DIR / "analysis_results"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

ARQUIVO_SEM_VV = (
    ROOT / "dados" / "outputs" / "estimacao_PV"
    / "Resultados_da_estimacao_por_clusters_FP1.xlsx"
)

ARQUIVO_COM_VV = (
    ROOT / "dados" / "outputs" / "estimacao_PV"
    / "Resultados_da_estimacao_por_clusters_VV.xlsx"
)

plt.rcParams["figure.dpi"] = 150
plt.rcParams["savefig.dpi"] = 300
plt.rcParams["font.size"] = 12


# ==========================================================
# Read data
# ==========================================================

if not ARQUIVO_SEM_VV.exists():
    raise FileNotFoundError(
        f"Without Volt-VAr result file not found: {ARQUIVO_SEM_VV}"
    )

if not ARQUIVO_COM_VV.exists():
    raise FileNotFoundError(
        f"With Volt-VAr result file not found: {ARQUIVO_COM_VV}"
    )

resultados_sem_vv = pd.read_excel(ARQUIVO_SEM_VV)
resultados_com_vv = pd.read_excel(ARQUIVO_COM_VV)

resultados_sem_vv["Condição"] = "Without Volt-VAr"
resultados_com_vv["Condição"] = "With Volt-VAr"

resultados = pd.concat(
    [resultados_sem_vv, resultados_com_vv],
    ignore_index=True
)


# ==========================================================
# Best cluster for each coefficient and scenario
# ==========================================================

melhores = (
    resultados
    .sort_values("Erro (%)")
    .groupby(["k", "Cenário"], as_index=False)
    .first()
)


# ==========================================================
# Best results with and without Volt-VAr
# ==========================================================

melhores_sem_vv = (
    resultados_sem_vv.sort_values("Erro (%)")
    .groupby("Cenário", as_index=False)
    .first()
)

melhores_com_vv = (
    resultados_com_vv.sort_values("Erro (%)")
    .groupby("Cenário", as_index=False)
    .first()
)

comparacao = melhores_sem_vv.merge(
    melhores_com_vv,
    on="Cenário",
    suffixes=(" - Without Volt-VAr", " - With Volt-VAr")
)

comparacao["Diferença de erro (p.p.)"] = (
    comparacao["Erro (%) - With Volt-VAr"]
    - comparacao["Erro (%) - Without Volt-VAr"]
)

comparacao["Diferença de acerto (p.p.)"] = (
    comparacao["Acerto (%) - With Volt-VAr"]
    - comparacao["Acerto (%) - Without Volt-VAr"]
)

comparacao["Variação relativa do erro (%)"] = (
    comparacao["Diferença de erro (p.p.)"]
    / comparacao["Erro (%) - Without Volt-VAr"]
    * 100
)

tabela_comparacao = comparacao.rename(
    columns={
        "Cenário": "PV Penetration (%)",
        "Cluster - Without Volt-VAr": "Best Cluster - Without Volt-VAr",
        "Cluster - With Volt-VAr": "Best Cluster - With Volt-VAr",
        "k - Without Volt-VAr": "k - Without Volt-VAr",
        "k - With Volt-VAr": "k - With Volt-VAr",
        "Potência Real (kW) - Without Volt-VAr": "Actual PV Capacity (kW)",
        "Potência estimada (kW) - Without Volt-VAr":
            "Estimated PV Capacity - Without Volt-VAr (kW)",
        "Erro (%) - Without Volt-VAr": "Error - Without Volt-VAr (%)",
        "Acerto (%) - Without Volt-VAr": "Accuracy - Without Volt-VAr (%)",
        "Potência estimada (kW) - With Volt-VAr":
            "Estimated PV Capacity - With Volt-VAr (kW)",
        "Erro (%) - With Volt-VAr": "Error - With Volt-VAr (%)",
        "Acerto (%) - With Volt-VAr": "Accuracy - With Volt-VAr (%)",
    }
)

# ==========================================================
# Comparative figure — estimation error
# ==========================================================

plt.figure(figsize=(8, 5))

plt.plot(
    tabela_comparacao["PV Penetration (%)"],
    tabela_comparacao["Error - Without Volt-VAr (%)"],
    marker="o", linewidth=2, label="Without Volt-VAr"
)

plt.plot(
    tabela_comparacao["PV Penetration (%)"],
    tabela_comparacao["Error - With Volt-VAr (%)"],
    marker="o", linewidth=2, label="With Volt-VAr"
)

plt.xlabel("PV Penetration (%)")
plt.ylabel("Estimation Error (%)")
plt.title("Estimation Error: Without vs. With Volt-VAr")
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.savefig(
    OUTPUT_DIR / "Comparison_Error_Without_vs_With_VoltVar.png",
    bbox_inches="tight"
)
plt.close()

# ==========================================================
# Comparative figure — accuracy
# ==========================================================

plt.figure(figsize=(8, 5))

plt.plot(
    tabela_comparacao["PV Penetration (%)"],
    tabela_comparacao["Accuracy - Without Volt-VAr (%)"],
    marker="o", linewidth=2, label="Without Volt-VAr"
)

plt.plot(
    tabela_comparacao["PV Penetration (%)"],
    tabela_comparacao["Accuracy - With Volt-VAr (%)"],
    marker="o", linewidth=2, label="With Volt-VAr"
)

plt.xlabel("PV Penetration (%)")
plt.ylabel("Accuracy (%)")
plt.title("Estimation Accuracy: Without vs. With Volt-VAr")
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.savefig(
    OUTPUT_DIR / "Comparison_Accuracy_Without_vs_With_VoltVar.png",
    bbox_inches="tight"
)
plt.close()

# ==========================================================
# Save direct comparison
# ==========================================================

comparacao_excel = OUTPUT_DIR / "Comparison_FP1_vs_VoltVar.xlsx"

with pd.ExcelWriter(comparacao_excel, engine="openpyxl") as writer:
    tabela_comparacao.to_excel(
        writer, sheet_name="Comparison", index=False
    )
    melhores_sem_vv.to_excel(
        writer, sheet_name="Without_VoltVar", index=False
    )
    melhores_com_vv.to_excel(
        writer, sheet_name="With_VoltVar", index=False
    )

comparacao_csv = OUTPUT_DIR / "Comparison_FP1_vs_VoltVar.csv"
tabela_comparacao.to_csv(comparacao_csv, index=False)

comparacao_txt = OUTPUT_DIR / "Comparison_Summary.txt"

erro_medio_sem = (
    melhores_sem_vv["Erro (%)"].mean()
)

erro_medio_com = (
    melhores_com_vv["Erro (%)"].mean()
)

with open(comparacao_txt, "w", encoding="utf-8") as f:
    f.write("=" * 90 + "\n")
    f.write("FP1 vs. VOLT-VAR COMPARISON\n")
    f.write("=" * 90 + "\n\n")
    f.write(f"Without Volt-VAr file:\n{ARQUIVO_SEM_VV}\n\n")
    f.write(f"With Volt-VAr file:\n{ARQUIVO_COM_VV}\n\n")
    f.write("BEST RESULTS BY PV PENETRATION\n\n")
    f.write(tabela_comparacao.to_string(index=False))
    f.write("\n\n")
    f.write(f"Mean error without Volt-VAr: {erro_medio_sem:.3f}%\n")
    f.write(f"Mean error with Volt-VAr:    {erro_medio_com:.3f}%\n")
    f.write(
        f"Mean difference (with - without): "
        f"{erro_medio_com - erro_medio_sem:.3f} percentage points\n"
    )
    f.write(
        "\nIMPORTANT: this comparison must use results obtained after "
        "the correct clusterization step.\n"
    )

# ==========================================================
# Figure 1
# Estimation Error vs. Adjustment Coefficient
# ==========================================================

plt.figure(figsize=(8, 5))

for cenario in sorted(melhores["Cenário"].unique()):
    dados = melhores[melhores["Cenário"] == cenario]

    plt.plot(
        dados["k"],
        dados["Erro (%)"],
        marker="o",
        linewidth=2,
        label=f"{cenario}% PV",
    )

plt.xlabel("Adjustment Coefficient (k)")
plt.ylabel("Estimation Error (%)")
plt.title("Estimation Error vs. Adjustment Coefficient")
plt.grid(True)
plt.legend(title="PV Penetration")
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "Error_vs_k.png", bbox_inches="tight")
plt.close()


# ==========================================================
# Figure 2
# Estimated PV Capacity vs. Adjustment Coefficient
# ==========================================================

plt.figure(figsize=(8, 5))

for cenario in sorted(melhores["Cenário"].unique()):
    dados = melhores[melhores["Cenário"] == cenario]

    plt.plot(
        dados["k"],
        dados["Potência estimada (kW)"],
        marker="o",
        linewidth=2,
        label=f"{cenario}% PV",
    )

    plt.axhline(
        dados["Potência Real (kW)"].iloc[0],
        linestyle="--",
    )

plt.xlabel("Adjustment Coefficient (k)")
plt.ylabel("Estimated PV Capacity (kW)")
plt.title("Estimated PV Capacity vs. Adjustment Coefficient")
plt.grid(True)
plt.legend(title="PV Penetration")
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "EstimatedPower_vs_k.png", bbox_inches="tight")
plt.close()


# ==========================================================
# Figure 3
# Mean Estimation Error vs. Adjustment Coefficient
# ==========================================================

media = (
    resultados
    .groupby("k")["Erro (%)"]
    .mean()
    .reset_index()
)

plt.figure(figsize=(8, 5))

plt.plot(
    media["k"],
    media["Erro (%)"],
    marker="o",
    linewidth=2,
)

idx = media["Erro (%)"].idxmin()
k_otimo = media.loc[idx, "k"]
erro_otimo = media.loc[idx, "Erro (%)"]

plt.axvline(
    k_otimo,
    linestyle="--",
    label=f"Optimal k = {k_otimo:.2f}",
)

plt.scatter(
    k_otimo,
    erro_otimo,
    s=80,
)

plt.xlabel("Adjustment Coefficient (k)")
plt.ylabel("Mean Estimation Error (%)")
plt.title("Mean Estimation Error vs. Adjustment Coefficient")
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "MeanError_vs_k.png", bbox_inches="tight")
plt.close()


# ==========================================================
# Figure 4
# Estimation Accuracy vs. Adjustment Coefficient
# ==========================================================

plt.figure(figsize=(8, 5))

for cenario in sorted(melhores["Cenário"].unique()):
    dados = melhores[melhores["Cenário"] == cenario]

    plt.plot(
        dados["k"],
        dados["Acerto (%)"],
        marker="o",
        linewidth=2,
        label=f"{cenario}% PV",
    )

plt.xlabel("Adjustment Coefficient (k)")
plt.ylabel("Accuracy (%)")
plt.title("Estimation Accuracy vs. Adjustment Coefficient")
plt.grid(True)
plt.legend(title="PV Penetration")
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "Accuracy_vs_k.png", bbox_inches="tight")
plt.close()


# ==========================================================
# Best result for each PV penetration scenario
# ==========================================================

melhor_cenario = (
    resultados
    .sort_values("Erro (%)")
    .groupby("Cenário", as_index=False)
    .first()
)

tabela_artigo = melhor_cenario[
    [
        "Cenário",
        "Cluster",
        "k",
        "Potência Real (kW)",
        "Potência estimada (kW)",
        "Erro (%)",
        "Acerto (%)",
        "RMSE",
        "MAE",
        "R²",
        "Equações",
    ]
].copy()

# English column names for analysis outputs
tabela_artigo = tabela_artigo.rename(
    columns={
        "Cenário": "PV Penetration (%)",
        "Cluster": "Best Cluster",
        "k": "Adjustment Coefficient (k)",
        "Potência Real (kW)": "Actual PV Capacity (kW)",
        "Potência estimada (kW)": "Estimated PV Capacity (kW)",
        "Erro (%)": "Estimation Error (%)",
        "Acerto (%)": "Accuracy (%)",
        "Equações": "Number of Equations",
    }
)

# Numeric formatting only for presentation/export
tabela_formatada = tabela_artigo.copy()
tabela_formatada["Adjustment Coefficient (k)"] = (
    tabela_formatada["Adjustment Coefficient (k)"].map("{:.2f}".format)
)
tabela_formatada["Actual PV Capacity (kW)"] = (
    tabela_formatada["Actual PV Capacity (kW)"].map("{:.2f}".format)
)
tabela_formatada["Estimated PV Capacity (kW)"] = (
    tabela_formatada["Estimated PV Capacity (kW)"].map("{:.2f}".format)
)
tabela_formatada["Estimation Error (%)"] = (
    tabela_formatada["Estimation Error (%)"].map("{:.2f}".format)
)
tabela_formatada["Accuracy (%)"] = (
    tabela_formatada["Accuracy (%)"].map("{:.2f}".format)
)
tabela_formatada["RMSE"] = tabela_formatada["RMSE"].map("{:.3f}".format)
tabela_formatada["MAE"] = tabela_formatada["MAE"].map("{:.3f}".format)
tabela_formatada["R²"] = tabela_formatada["R²"].map("{:.5f}".format)


# ==========================================================
# Save tables
# ==========================================================

excel_file = OUTPUT_DIR / "Best_Estimation_Results.xlsx"
latex_file = OUTPUT_DIR / "Best_Estimation_Results.tex"
csv_file = OUTPUT_DIR / "Best_Estimation_Results.csv"

tabela_formatada.to_excel(excel_file, index=False)
tabela_formatada.to_csv(csv_file, index=False)

with open(latex_file, "w", encoding="utf-8") as f:
    f.write(
        tabela_formatada.to_latex(
            index=False,
            escape=False,
            caption="Best estimation results obtained for each PV penetration scenario.",
            label="tab:best_results",
        )
    )


# ==========================================================
# Save complete text report
# ==========================================================

report_file = OUTPUT_DIR / "Analysis_Summary.txt"

with open(report_file, "w", encoding="utf-8") as f:
    f.write("=" * 90 + "\n")
    f.write("PV ESTIMATION ANALYSIS SUMMARY\n")
    f.write("=" * 90 + "\n\n")

    f.write(f"Input file — Without Volt-VAr:\n{ARQUIVO_SEM_VV}\n")
    f.write(f"Input file — With Volt-VAr:\n{ARQUIVO_COM_VV}\n\n")
    f.write(f"Optimal adjustment coefficient (k): {k_otimo:.2f}\n")
    f.write(f"Minimum mean estimation error: {erro_otimo:.3f}%\n\n")

    f.write("=" * 90 + "\n")
    f.write("BEST RESULT FOR EACH PV PENETRATION SCENARIO\n")
    f.write("=" * 90 + "\n\n")

    f.write(tabela_formatada.to_string(index=False))
    f.write("\n\n")

    f.write("=" * 90 + "\n")
    f.write("FIGURES GENERATED\n")
    f.write("=" * 90 + "\n")
    f.write("1. Error_vs_k.png\n")
    f.write("2. EstimatedPower_vs_k.png\n")
    f.write("3. MeanError_vs_k.png\n")
    f.write("4. Accuracy_vs_k.png\n")


# ==========================================================
# Console output
# ==========================================================

print("=" * 80)
print("PV ESTIMATION ANALYSIS")
print("=" * 80)
print(f"Optimal adjustment coefficient (k): {k_otimo:.2f}")
print(f"Minimum mean estimation error     : {erro_otimo:.3f}%")
print("=" * 80)

print("\nBEST RESULTS FOR EACH PV PENETRATION SCENARIO")
print("=" * 100)
print(tabela_formatada.to_string(index=False))
print("=" * 100)

print("\nCOMPARISON — WITHOUT vs. WITH VOLT-VAR")
print("=" * 100)
print(tabela_comparacao.to_string(index=False))
print("=" * 100)
print(f"Mean error without Volt-VAr: {erro_medio_sem:.3f}%")
print(f"Mean error with Volt-VAr   : {erro_medio_com:.3f}%")
print(
    f"Mean difference (with - without): "
    f"{erro_medio_com - erro_medio_sem:.3f} percentage points"
)

print("\nAnalysis files saved to:")
print(OUTPUT_DIR)
print("\nGenerated files:")
for arquivo in sorted(OUTPUT_DIR.iterdir()):
    print(f"  - {arquivo.name}")
