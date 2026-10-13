# %%
import pandas as pd

from pathlib import Path

# ============================================================
# CONFIGURAÇÃO
# ============================================================

ARQUIVO = Path("Multiple_Executions_Final_Analysis.xlsx")

# FP1 = fator de potência unitário
# VV   = Volt-VAr
CONDICAO = "FP1"


# ============================================================
# LEITURA
# ============================================================

df = pd.read_excel(
    ARQUIVO,
    sheet_name="Final_Results"
)

df.columns = [str(c).strip() for c in df.columns]


# ============================================================
# VERIFICAÇÃO
# ============================================================

colunas_necessarias = [
    "k",
    "Condition",
    "Cenário",
    "Erro (%)"
]

faltantes = [
    c for c in colunas_necessarias
    if c not in df.columns
]

if faltantes:
    raise ValueError(
        f"Colunas não encontradas: {faltantes}\n\n"
        f"Colunas disponíveis:\n{list(df.columns)}"
    )


# ============================================================
# CONVERSÃO DOS DADOS
# ============================================================

df["k"] = pd.to_numeric(df["k"])
df["Cenário"] = pd.to_numeric(df["Cenário"])
df["Erro (%)"] = pd.to_numeric(df["Erro (%)"])

df["Condition"] = (
    df["Condition"]
    .astype(str)
    .str.strip()
)


# ============================================================
# FILTRO DA CONDIÇÃO
# ============================================================

dados = df[
    df["Condition"] == CONDICAO
].copy()

if dados.empty:
    raise ValueError(
        f"Nenhum resultado encontrado para "
        f"Condition = {CONDICAO}"
    )


# ============================================================
# RESUMO
# ============================================================

resumo = (
    dados
    .groupby(["k", "Cenário"])["Erro (%)"]
    .agg(
        Média="mean",
        Mínimo="min",
        Máximo="max",
        N="count"
    )
    .reset_index()
    .sort_values(["k", "Cenário"])
)


# ============================================================
# RESULTADO NO TERMINAL
# ============================================================

print()
print("=" * 80)
print(f"RESUMO DOS RESULTADOS — {CONDICAO}")
print("=" * 80)

for k, grupo in resumo.groupby("k"):

    print()
    print(f"k = {k:.2f}")
    print("-" * 80)

    print(
        f"{'Cenário':>10} | "
        f"{'Média (%)':>12} | "
        f"{'Mínimo (%)':>12} | "
        f"{'Máximo (%)':>12} | "
        f"{'N':>3}"
    )

    print("-" * 80)

    for _, linha in grupo.iterrows():

        print(
            f"{int(linha['Cenário']):>10} | "
            f"{linha['Média']:>12.3f} | "
            f"{linha['Mínimo']:>12.3f} | "
            f"{linha['Máximo']:>12.3f} | "
            f"{int(linha['N']):>3}"
        )

    print("-" * 80)


# ============================================================
# TABELA FINAL
# ============================================================

print()
print("TABELA COMPLETA")
print()

tabela = resumo.copy()

tabela.columns = [
    "k",
    "PV Penetration (%)",
    "Mean Error (%)",
    "Min. Error (%)",
    "Max. Error (%)",
    "N"
]

print(
    tabela.to_string(
        index=False,
        formatters={
            "k": "{:.2f}".format,
            "Mean Error (%)": "{:.3f}".format,
            "Min. Error (%)": "{:.3f}".format,
            "Max. Error (%)": "{:.3f}".format
        }
    )
)

print()
print(f"Total de combinações: {len(tabela)}")
print(
    "Os valores foram calculados diretamente da aba "
    "'Final_Results', utilizando os resultados finais de cada execução."
)