#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Oct  9 11:35:28 2026

@author: matheus
"""

import pandas as pd

# Arquivo de resultados
arquivo = "Resultados_Kara_PVWatts_todas_execucoes.xlsx"

# Carrega os resultados
df = pd.read_excel(arquivo)

# Seleciona somente as simulações de um ano (8760 horas)
df_ano = df[df["Horas_janela"] == 8760].copy()

# Calcula o erro absoluto
df_ano["erro_abs"] = df_ano["erro_percentual"].abs()

# Calcula as estatísticas por condição do inversor e penetração PV
resultados = (
    df_ano
    .groupby(["VoltVar", "Penetracao_percent"])["erro_abs"]
    .agg(
        quantidade="count",
        erro_medio="mean",
        erro_minimo="min",
        erro_maximo="max"
    )
    .reset_index()
)

# Organiza e imprime os resultados
for voltvar, nome_condicao in [
    (False, "FP = 1"),
    (True, "Volt-VAr")
]:
    tabela = resultados[resultados["VoltVar"] == voltvar].copy()

    tabela = tabela.rename(columns={
        "Penetracao_percent": "Penetração PV (%)",
        "quantidade": "Execuções",
        "erro_medio": "Erro médio (%)",
        "erro_minimo": "Erro mínimo (%)",
        "erro_maximo": "Erro máximo (%)"
    })

    tabela = tabela.drop(columns=["VoltVar", "Execuções"])

    print(f"\n{'=' * 55}")
    print(f"Condição do inversor: {nome_condicao}")
    print(f"{'=' * 55}")

    print(
        tabela.round(3).to_string(
            index=False,
            formatters={
                "Erro médio (%)": "{:.3f}".format,
                "Erro mínimo (%)": "{:.3f}".format,
                "Erro máximo (%)": "{:.3f}".format
            }
        )
    )

# Salva os resultados em um novo arquivo
resultados.to_csv(
    "erros_Kara_ano.csv",
    index=False,
    decimal=",",
    sep=";",
    encoding="utf-8-sig"
)

print("\nResultados salvos em erros_Kara_ano.csv")