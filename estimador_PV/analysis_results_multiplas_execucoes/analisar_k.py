import pandas as pd
from pathlib import Path

# ============================================================
# CONFIGURAÇÃO
# ============================================================

ARQUIVO = Path("Multiple_Executions_Final_Analysis.xlsx")


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
# CONVERSÃO
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
# ANÁLISE POR k
# ============================================================
#
# Para cada k e condição:
#   - calcula o erro médio considerando todas as execuções
#     dos três cenários;
#   - calcula o menor erro;
#   - calcula o maior erro;
#   - informa o número de resultados.
#
# Como existem 10 execuções para cada cenário, o resultado
# também pode ser interpretado como a média dos três erros
# médios dos cenários.
# ============================================================

resumo_k = (
    df
    .groupby(["Condition", "k"])["Erro (%)"]
    .agg(
        Média="mean",
        Mínimo="min",
        Máximo="max",
        N="count"
    )
    .reset_index()
    .sort_values(["Condition", "k"])
)


# ============================================================
# MÉDIA DOS CENÁRIOS
# ============================================================
#
# Esta tabela é uma segunda forma de conferir o resultado:
# primeiro calcula a média de cada cenário para cada k e,
# depois, calcula a média dos três cenários.
#
# Os valores devem ser iguais aos da análise acima, pois há
# exatamente o mesmo número de execuções (10) em cada cenário.
# ============================================================

media_cenarios = (
    df
    .groupby(["Condition", "k", "Cenário"])["Erro (%)"]
    .mean()
    .reset_index()
)

media_cenarios = (
    media_cenarios
    .groupby(["Condition", "k"])["Erro (%)"]
    .mean()
    .reset_index(name="Média dos 3 cenários (%)")
)


# ============================================================
# JUNTA AS DUAS FORMAS DE CÁLCULO
# ============================================================

resultado = resumo_k.merge(
    media_cenarios,
    on=["Condition", "k"],
    how="left"
)

resultado["Diferença entre cálculos (%)"] = (
    resultado["Média"]
    - resultado["Média dos 3 cenários (%)"]
).abs()


# ============================================================
# MOSTRA RESULTADOS
# ============================================================

print()
print("=" * 90)
print("ANÁLISE DO PARÂMETRO k")
print("=" * 90)

for condicao, grupo in resultado.groupby("Condition"):

    print()
    print(f"CONDIÇÃO: {condicao}")
    print("-" * 90)

    print(
        f"{'k':>6} | "
        f"{'Média (%)':>12} | "
        f"{'Mínimo (%)':>12} | "
        f"{'Máximo (%)':>12} | "
        f"{'N':>4}"
    )

    print("-" * 90)

    for _, linha in grupo.iterrows():

        print(
            f"{linha['k']:>6.2f} | "
            f"{linha['Média']:>12.3f} | "
            f"{linha['Mínimo']:>12.3f} | "
            f"{linha['Máximo']:>12.3f} | "
            f"{int(linha['N']):>4}"
        )

    print("-" * 90)


# ============================================================
# VERIFICAÇÃO DA CONTRAPROVA
# ============================================================

print()
print("=" * 90)
print("CONTRAPROVA — MÉDIA DIRETA x MÉDIA DOS 3 CENÁRIOS")
print("=" * 90)

print(
    resultado[
        [
            "Condition",
            "k",
            "Média",
            "Média dos 3 cenários (%)",
            "Diferença entre cálculos (%)"
        ]
    ].to_string(
        index=False,
        formatters={
            "k": "{:.2f}".format,
            "Média": "{:.6f}".format,
            "Média dos 3 cenários (%)": "{:.6f}".format,
            "Diferença entre cálculos (%)": "{:.10f}".format
        }
    )
)

print()
print(
    "A diferença deve ser zero (ou apenas um valor numérico "
    "residual de arredondamento)."
)


# ============================================================
# MELHOR k POR CONDIÇÃO
# ============================================================

print()
print("=" * 90)
print("k COM MENOR ERRO MÉDIO")
print("=" * 90)

for condicao, grupo in resultado.groupby("Condition"):

    melhor = grupo.loc[grupo["Média"].idxmin()]

    print(
        f"{condicao}: k = {melhor['k']:.2f} "
        f"-> erro médio = {melhor['Média']:.3f}%"
    )


# ============================================================
# TABELA FINAL
# ============================================================

print()
print("TABELA FINAL")
print()

tabela = resultado[
    [
        "Condition",
        "k",
        "Média",
        "Mínimo",
        "Máximo",
        "N"
    ]
].copy()

tabela.columns = [
    "Condition",
    "k",
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
print(f"Total de combinações k × condição: {len(tabela)}")
print(
    "Os valores foram calculados diretamente da aba "
    "'Final_Results', utilizando os resultados finais de cada execução."
)
