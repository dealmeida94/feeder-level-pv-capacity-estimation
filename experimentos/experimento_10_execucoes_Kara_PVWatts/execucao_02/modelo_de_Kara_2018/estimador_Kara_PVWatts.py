#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Estimador de potência FV baseado no modelo linear de Kara et al. (2018),
adaptado à arquitetura atual do projeto BtM-PV-estimating.

ADAPTAÇÕES IMPORTANTES
----------------------
1. O artigo de Kara utiliza um "irradiance proxy", originalmente associado
   à potência de uma instalação FV monitorada. Neste projeto, o proxy é a
   saída normalizada do PVWatts utilizada para gerar o PVShape.dss.

2. O controlador geral atual trabalha com dados horários. Portanto, este
   estimador NÃO interpola P ou Q para criar medições de 5 minutos.

3. São avaliadas três janelas temporais:
       - 1 mês  : 744 h (jan/2017)
       - 6 meses: 4344 h (jan-jun/2017)
       - 1 ano  : 8760 h (2017)

4. O estimador não utiliza P_PV dos resultados da simulação para realizar
   a estimação. Essa coluna é mantida apenas como referência/ground truth
   para análises posteriores. O regressor solar é o proxy PVWatts.

MODELO
------
    P(t) = k_eff Q(t) - C_eff phi(t) + R + epsilon(t)

onde:
    P       = potência ativa líquida no alimentador [kW]
    Q       = potência reativa líquida no alimentador [kvar]
    phi     = saída normalizada do PVWatts [pu]
    C_eff   = potência FV estimada [kW]
    k_eff   = coeficiente do modelo de carga
    R       = intercepto [kW]

A geração FV instantânea estimada é:

    P_PV_hat(t) = k_eff Q(t) + R - P(t)

NOTA SOBRE O SINAL
------------------
O controlador geral grava P = -Circuit.TotalPower(), de modo que consumo
líquido é positivo. Assim, geração FV reduz P. Por isso usamos -phi na
matriz de regressão e reportamos C_eff como potência FV positiva.

COMPATIBILIDADE COM A ARQUITETURA ATUAL
---------------------------------------
O controlador geral:
    - usa cfg.MASTER_BL;
    - usa cfg.PVSHAPE;
    - salva resultados em cfg.OUT_PV;
    - grava a coluna "Irradiancia_pu" a partir do vetor mult do PVShape.

O PVShape atual é gerado pelo módulo pvwatts.py a partir da potência AC
normalizada do modelo PVWatts. Portanto, neste estimador a coluna
"Irradiancia_pu" é interpretada corretamente como "proxy_PVWatts_pu",
e não como irradiância física em W/m².
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import numpy as np
import pandas as pd
import sys

PASTA_ESTIMADOR = Path(__file__).resolve().parent
RAIZ_PROJETO = PASTA_ESTIMADOR.parent

if str(RAIZ_PROJETO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROJETO))

import configs as cfg

# ============================================================================
# CONFIGURAÇÕES DO EXPERIMENTO
# ============================================================================

# "FP1"    -> somente resultados sem Volt-VAr
# "VV"     -> somente resultados Volt-VAr
# "TODOS"  -> processa os dois tipos
TIPO_CENARIO = "TODOS"

# Janelas contíguas iniciando em 01/01/2017.
# O conjunto original possui 8760 horas de 2017.
JANELAS_TEMPORAIS = {
    "1_mes": 31 * 24,       # janeiro = 744 h
    "6_meses": 181 * 24,    # janeiro-junho = 4344 h
    "ano": 365 * 24,        # 8760 h
}

# Horas solares.
# O Kara trabalha apenas no período em que existe sinal solar.
# Como o proxy PVWatts já é zero à noite, usamos phi > 0.
MINIMO_OBSERVACOES = 4

# Nome da coluna produzida pelo controlador geral.
COLUNA_PROXY_ATUAL = "Irradiancia_pu"


# ============================================================================
# LOCALIZAÇÃO DE RESULTADOS
# ============================================================================

def localizar_resultados():
    """
    Localiza os resultados produzidos pelo controlador geral atual.

    Padrões esperados:
        resultados20.parquet
        resultados40.parquet
        resultados60.parquet
        resultados20_VV.parquet
        resultados40_VV.parquet
        resultados60_VV.parquet
    """

    pasta = cfg.OUT_PV

    if not pasta.exists():
        raise FileNotFoundError(
            f"Pasta de resultados não encontrada: {pasta}"
        )

    arquivos = sorted(pasta.glob("resultados*.parquet"))

    resultados = []

    padrao = re.compile(
        r"^resultados(?P<nivel>\d+(?:\.\d+)?)(?P<vv>_VV)?$",
        re.IGNORECASE,
    )

    for arquivo in arquivos:
        match = padrao.fullmatch(arquivo.stem)

        if not match:
            print(f"Ignorando arquivo com nome não reconhecido: {arquivo.name}")
            continue

        nivel = float(match.group("nivel"))
        volt_var = match.group("vv") is not None

        if TIPO_CENARIO.upper() == "FP1" and volt_var:
            continue

        if TIPO_CENARIO.upper() == "VV" and not volt_var:
            continue

        resultados.append(
            {
                "nivel": nivel,
                "volt_var": volt_var,
                "nome": (
                    f"{int(nivel)}_VV"
                    if volt_var
                    else f"{int(nivel)}"
                ),
                "arquivo": arquivo,
            }
        )

    if not resultados:
        raise FileNotFoundError(
            f"Nenhum resultado compatível com TIPO_CENARIO={TIPO_CENARIO} "
            f"foi encontrado em {pasta}"
        )

    resultados.sort(
        key=lambda x: (x["nivel"], x["volt_var"])
    )

    print("\nResultados encontrados:")
    for item in resultados:
        tipo = "Volt-VAr" if item["volt_var"] else "FP=1"
        print(
            f"  {item['arquivo'].name:<35} "
            f"| {item['nivel']:.0f}% | {tipo}"
        )

    return resultados


# ============================================================================
# LEITURA DOS RESULTADOS
# ============================================================================

def ler_resultados(lista_resultados):
    resultados = {}

    for item in lista_resultados:
        df = pd.read_parquet(item["arquivo"])

        colunas_obrigatorias = {
            "hora",
            "P_kW",
            "Q_kvar",
            COLUNA_PROXY_ATUAL,
        }

        ausentes = colunas_obrigatorias.difference(df.columns)

        if ausentes:
            raise KeyError(
                f"O arquivo {item['arquivo'].name} não possui as colunas "
                f"obrigatórias: {sorted(ausentes)}"
            )

        resultados[item["nome"]] = df.copy()

    return resultados


# ============================================================================
# POTÊNCIAS REAIS DOS CENÁRIOS
# ============================================================================

def carregar_potencias_reais():
    """
    Lê cfg.POTENCIAS_CENARIOS.

    A função aceita os nomes de coluna usados nas diferentes versões
    do projeto:
        Cenario / cenario
        Potencia_inserida_kW / potencia_PV_kW / Potencia
    """

    arquivo = cfg.POTENCIAS_CENARIOS

    if not arquivo.exists():
        raise FileNotFoundError(
            f"Arquivo de potências reais não encontrado:\n{arquivo}"
        )

    df = pd.read_excel(arquivo)

    coluna_cenario = next(
        (
            c
            for c in ["Cenario", "cenario", "CENARIO"]
            if c in df.columns
        ),
        None,
    )

    coluna_potencia = next(
        (
            c
            for c in [
                "Potencia_inserida_kW",
                "potencia_PV_kW",
                "Potencia",
                "Potencia_kW",
            ]
            if c in df.columns
        ),
        None,
    )

    if coluna_cenario is None:
        raise KeyError(
            f"Não foi encontrada coluna de cenário em {arquivo.name}. "
            f"Colunas disponíveis: {list(df.columns)}"
        )

    if coluna_potencia is None:
        raise KeyError(
            f"Não foi encontrada coluna de potência em {arquivo.name}. "
            f"Colunas disponíveis: {list(df.columns)}"
        )

    potencias = {}

    for _, linha in df.iterrows():
        nivel = int(float(linha[coluna_cenario]))
        potencias[nivel] = float(linha[coluna_potencia])

    print("\nPotências reais dos cenários:")
    for nivel in sorted(potencias):
        print(f"  {nivel}% -> {potencias[nivel]:.2f} kW")

    return potencias


# ============================================================================
# PREPARAÇÃO DO PROXY PVWATTS
# ============================================================================

def preparar_dataframe(df):
    """
    Prepara as variáveis utilizadas na regressão.

    O controlador atual salva:
        Irradiancia_pu = vetor 'mult' do PVShape.dss

    O PVShape é gerado a partir da saída AC normalizada do PVWatts.
    Portanto, renomeamos internamente a variável para deixar explícita
    sua função como proxy solar.
    """

    dados = df.copy()

    dados = dados.sort_values("hora").reset_index(drop=True)

    dados["proxy_PVWatts_pu"] = pd.to_numeric(
        dados[COLUNA_PROXY_ATUAL],
        errors="coerce",
    )

    dados["P_kW"] = pd.to_numeric(
        dados["P_kW"],
        errors="coerce",
    )

    dados["Q_kvar"] = pd.to_numeric(
        dados["Q_kvar"],
        errors="coerce",
    )

    dados = dados.replace(
        [np.inf, -np.inf],
        np.nan,
    ).dropna(
        subset=[
            "P_kW",
            "Q_kvar",
            "proxy_PVWatts_pu",
        ]
    )

    # O PVWatts/PVShape deve estar entre 0 e 1 pu.
    if (
        (dados["proxy_PVWatts_pu"] < -1e-9).any()
        or
        (dados["proxy_PVWatts_pu"] > 1.0 + 1e-9).any()
    ):
        raise ValueError(
            "O proxy PVWatts não está normalizado entre 0 e 1 pu."
        )

    # Evita pequenos resíduos numéricos negativos.
    dados["proxy_PVWatts_pu"] = np.clip(
        dados["proxy_PVWatts_pu"].to_numpy(dtype=float),
        0.0,
        1.0,
    )

    return dados


# ============================================================================
# JANELAS TEMPORAIS
# ============================================================================

def aplicar_janela_temporal(df, numero_horas):
    """
    Seleciona as primeiras 'numero_horas' da série anual.

    Como o controlador grava a hora acumulada de 0 a 8759, a seleção
    é feita diretamente nessa coluna, preservando a ordem temporal.
    """

    if "hora" not in df.columns:
        raise KeyError("A coluna 'hora' não existe.")

    dados = df.loc[
        df["hora"].between(0, numero_horas - 1)
    ].copy()

    if len(dados) < numero_horas:
        raise ValueError(
            f"Dados insuficientes para a janela de {numero_horas} h: "
            f"encontradas {len(dados)} h."
        )

    return dados.reset_index(drop=True)


# ============================================================================
# MODELO LINEAR DE KARA
# ============================================================================

def estimar_kara(
    dados,
    potencia_real=None,
):
    """
    Ajusta o modelo linear de Kara:

        P = k_eff Q - C_eff phi + R + epsilon

    onde phi é o proxy PVWatts normalizado.

    A potência FV estimada é C_eff [kW].
    """

    dados = preparar_dataframe(dados)

    # Kara utiliza somente o período com geração solar.
    dados = dados.loc[
        dados["proxy_PVWatts_pu"] > 0
    ].copy()

    if len(dados) < MINIMO_OBSERVACOES:
        raise ValueError(
            "Dados insuficientes para a regressão de Kara."
        )

    P = dados["P_kW"].to_numpy(dtype=float)
    Q = dados["Q_kvar"].to_numpy(dtype=float)
    phi = dados["proxy_PVWatts_pu"].to_numpy(dtype=float)

    # P = k Q - C phi + R
    A = np.column_stack(
        (
            Q,
            -phi,
            np.ones(len(phi)),
        )
    )

    beta, residuals, rank, singular_values = np.linalg.lstsq(
        A,
        P,
        rcond=None,
    )

    k_eff = float(beta[0])
    C_eff = float(beta[1])
    R = float(beta[2])

    P_modelo = A @ beta
    erro_modelo = P - P_modelo

    # Reconstrução da carga.
    P_carga_estimada = (
        k_eff * Q +
        R
    )

    # Pela convenção do projeto, P é consumo líquido positivo.
    # Portanto:
    #     P_PV_hat = P_load_hat - P
    P_PV_estimada = (
        P_carga_estimada -
        P
    )

    SSE = float(np.sum(erro_modelo ** 2))

    n = len(P)
    numero_parametros = 3
    graus_liberdade = n - numero_parametros

    if graus_liberdade > 0:
        sigma2 = SSE / graus_liberdade
    else:
        sigma2 = np.nan

    # Covariância dos parâmetros.
    if (
        rank == A.shape[1]
        and graus_liberdade > 0
    ):
        try:
            cov_beta = (
                sigma2 *
                np.linalg.inv(A.T @ A)
            )

            variancia_C = float(cov_beta[1, 1])
            desvio_C = float(
                np.sqrt(max(variancia_C, 0.0))
            )

        except np.linalg.LinAlgError:
            variancia_C = np.nan
            desvio_C = np.nan

    else:
        variancia_C = np.nan
        desvio_C = np.nan

    rmse = float(
        np.sqrt(
            np.mean(
                erro_modelo ** 2
            )
        )
    )

    mae = float(
        np.mean(
            np.abs(erro_modelo)
        )
    )

    ss_tot = float(
        np.sum(
            (
                P -
                np.mean(P)
            ) ** 2
        )
    )

    if ss_tot > 0:
        r2 = float(
            1 -
            SSE /
            ss_tot
        )
    else:
        r2 = np.nan

    P_PV_positiva = np.maximum(
        P_PV_estimada,
        0.0,
    )

    resultado = {
        "potencia_estimada_kW": C_eff,
        "k_eff": k_eff,
        "C_eff": C_eff,
        "C_assinado_Kara": -C_eff,
        "R_kW": R,
        "RMSE_kW": rmse,
        "MAE_kW": mae,
        "R2": r2,
        "variancia_C_eff": variancia_C,
        "desvio_C_eff": desvio_C,
        "numero_observacoes": n,
        "graus_liberdade": graus_liberdade,
        "posto": int(rank),
        "P_PV_media_kW": float(
            np.mean(P_PV_estimada)
        ),
        "P_PV_max_kW": float(
            np.max(P_PV_estimada)
        ),
        "P_PV_max_positivo_kW": float(
            np.max(P_PV_positiva)
        ),
        "P_PV_integral_positivo_kWh": float(
            np.sum(P_PV_positiva)
        ),
    }

    if potencia_real is not None:
        erro_percentual = (
            100.0 *
            abs(
                C_eff -
                potencia_real
            )
            /
            potencia_real
            if potencia_real != 0
            else np.nan
        )

        resultado["potencia_real_kW"] = float(
            potencia_real
        )

        resultado["erro_percentual"] = float(
            erro_percentual
        )

        resultado["acerto_percentual"] = float(
            100.0 -
            erro_percentual
        )

    curva = dados.copy()

    curva["P_modelo_kW"] = P_modelo
    curva["P_carga_estimada_kW"] = P_carga_estimada
    curva["P_PV_estimada_kW"] = P_PV_estimada
    curva["erro_modelo_kW"] = erro_modelo

    return resultado, curva


# ============================================================================
# EXECUÇÃO
# ============================================================================

def main():

    inicio = time.perf_counter()

    print("\n" + "=" * 78)
    print("KARA 2018 - ESTIMADOR ADAPTADO AO PROXY PVWATTS")
    print("=" * 78)

    print(f"\nProjeto: {cfg.RAIZ_DIR}")
    print(f"Resultados: {cfg.OUT_PV}")
    print(f"Potências reais: {cfg.POTENCIAS_CENARIOS}")
    print(f"Ambientes processados: {TIPO_CENARIO}")
    if TIPO_CENARIO.upper() == "TODOS":
        print("  - FP=1")
        print("  - Volt-VAr")

    print(f"Saída da planilha: {Path(__file__).resolve().parent}")

    print("\nJanelas temporais:")
    for nome, horas in JANELAS_TEMPORAIS.items():
        print(f"  {nome:<10} -> {horas} h")

    # ------------------------------------------------------------------
    # Localização e leitura
    # ------------------------------------------------------------------

    lista_resultados = localizar_resultados()
    resultados = ler_resultados(lista_resultados)
    potencias_reais = carregar_potencias_reais()

    # ------------------------------------------------------------------
    # Diretórios de saída
    # ------------------------------------------------------------------
    #
    # A planilha principal fica na MESMA PASTA deste script, para que
    # os resultados do teste possam ser encontrados junto ao estimador.
    # As curvas de diagnóstico continuam sendo gravadas em uma subpasta.
    #
    pasta_saida = Path(__file__).resolve().parent
    pasta_curvas = pasta_saida / "diagnostico_Kara_PVWatts"

    pasta_curvas.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ------------------------------------------------------------------
    # Estimação
    # ------------------------------------------------------------------

    resultados_finais = []

    print("\n" + "=" * 78)
    print("ESTIMAÇÕES")
    print("=" * 78)

    for item in lista_resultados:

        nome_cenario = item["nome"]
        nivel = int(item["nivel"])

        if nivel not in potencias_reais:
            print(
                f"\nIgnorando {nome_cenario}: "
                f"potência real não encontrada."
            )
            continue

        df_original = resultados[nome_cenario]

        potencia_real = potencias_reais[nivel]

        for nome_janela, numero_horas in JANELAS_TEMPORAIS.items():

            print("\n" + "-" * 78)
            print(
                f"Cenário: {nome_cenario} | "
                f"janela: {nome_janela} | "
                f"{numero_horas} h"
            )

            dados_janela = aplicar_janela_temporal(
                df_original,
                numero_horas,
            )

            resultado, curva = estimar_kara(
                dados_janela,
                potencia_real=potencia_real,
            )

            resultado.update(
                {
                    "Cenario": nome_cenario,
                    "Penetracao_percent": nivel,
                    "VoltVar": bool(item["volt_var"]),
                    "Janela": nome_janela,
                    "Horas_janela": numero_horas,
                    "Proxy_solar": "PVWatts_AC_normalizado",
                    "Resolucao_h": 1.0,
                }
            )

            resultados_finais.append(
                resultado
            )

            print(
                f"  Potência real     = "
                f"{potencia_real:.2f} kW"
            )

            print(
                f"  Potência estimada = "
                f"{resultado['potencia_estimada_kW']:.2f} kW"
            )

            print(
                f"  Erro              = "
                f"{resultado['erro_percentual']:.2f}%"
            )

            print(
                f"  k_eff             = "
                f"{resultado['k_eff']:.6f}"
            )

            print(
                f"  C_eff             = "
                f"{resultado['C_eff']:.2f} kW"
            )

            print(
                f"  R                 = "
                f"{resultado['R_kW']:.2f} kW"
            )

            print(
                f"  R²                = "
                f"{resultado['R2']:.4f}"
            )

            # Curva individual.
            arquivo_curva = (
                pasta_curvas /
                f"Kara_{nome_cenario}_{nome_janela}.xlsx"
            )

            curva.to_excel(
                arquivo_curva,
                index=False,
            )

    # ------------------------------------------------------------------
    # Consolidação
    # ------------------------------------------------------------------

    df_saida = pd.DataFrame(
        resultados_finais
    )

    arquivo_xlsx = (
        pasta_saida /
        "Resultados_Kara_PVWatts_FP1_VoltVar.xlsx"
    )

    arquivo_csv = (
        pasta_saida /
        "Resultados_Kara_PVWatts_FP1_VoltVar.csv"
    )

    with pd.ExcelWriter(arquivo_xlsx, engine="openpyxl") as writer:
        df_saida.to_excel(
            writer,
            sheet_name="Resultados",
            index=False,
        )

    df_saida.to_csv(
        arquivo_csv,
        index=False,
        sep=";",
        decimal=",",
    )

    # ------------------------------------------------------------------
    # Resumo por cenário/janela
    # ------------------------------------------------------------------

    if not df_saida.empty:

        colunas_resumo = [
            "Cenario",
            "Penetracao_percent",
            "VoltVar",
            "Janela",
            "Horas_janela",
            "potencia_real_kW",
            "potencia_estimada_kW",
            "erro_percentual",
            "k_eff",
            "C_eff",
            "R_kW",
            "RMSE_kW",
            "MAE_kW",
            "R2",
            "numero_observacoes",
        ]

        colunas_resumo = [
            c for c in colunas_resumo
            if c in df_saida.columns
        ]

        df_resumo = df_saida[
            colunas_resumo
        ].copy()

        arquivo_resumo = (
            pasta_saida /
            "Resumo_Kara_PVWatts.xlsx"
        )

        df_resumo.to_excel(
            arquivo_resumo,
            index=False,
        )

        # Também coloca o resumo dentro da planilha principal.
        with pd.ExcelWriter(
            arquivo_xlsx,
            engine="openpyxl",
            mode="a",
            if_sheet_exists="replace",
        ) as writer:
            df_resumo.to_excel(
                writer,
                sheet_name="Resumo",
                index=False,
            )

    tempo = time.perf_counter() - inicio

    print("\n" + "=" * 78)
    print("CONCLUÍDO")
    print("=" * 78)

    print(
        f"\nPlanilha consolidada (FP=1 + Volt-VAr):\n"
        f"  {arquivo_xlsx}"
    )

    print(
        f"\nCSV:\n"
        f"  {arquivo_csv}"
    )

    if not df_saida.empty:
        print("\nAmbientes presentes na planilha:")
        for vv in [False, True]:
            nome = "Volt-VAr" if vv else "FP=1"
            quantidade = int((df_saida["VoltVar"] == vv).sum())
            print(f"  {nome:<10}: {quantidade} resultados")

    print(
        f"\nDiagnósticos:\n"
        f"  {pasta_curvas}"
    )

    print(
        f"\nTempo de execução: {tempo:.2f} s"
    )

    return df_saida


if __name__ == "__main__":
    main()
