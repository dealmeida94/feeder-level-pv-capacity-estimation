#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Executa simulações anuais no OpenDSS para diferentes cenários
de inserção de geração fotovoltaica.

O script é capaz de executar automaticamente:

    - Caso Base (sem PV)
    - 10%
    - 20%
    - 30%
    - ou qualquer lista definida pelo usuário.

Para cada cenário são gerados:
    - arquivo parquet
    - gráficos
    - estatísticas

"""

import sys
import time
import re
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import opendssdirect as dss

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(ROOT))

import configs as cfg

from auxiliares import calc_tempo

# Garante que as pastas de saída existam antes de qualquer gravação.
cfg.OUT_PV.mkdir(parents=True, exist_ok=True)
cfg.FIGS_PV.mkdir(parents=True, exist_ok=True)

# INÍCIO DO TIMER
begin_timer = time.perf_counter()

print("\n" + "="*70)
print("VERIFICAÇÃO DOS CAMINHOS")
print("="*70)

print("RAIZ_DIR :", cfg.RAIZ_DIR)
print("MASTER_BL:", cfg.MASTER_BL)
print("PVSHAPE  :", cfg.PVSHAPE)
print("COM_PV   :", cfg.COM_PV)

print("\nArquivos existem?")
print("MASTER_BL:", cfg.MASTER_BL.exists())
print("PVSHAPE  :", cfg.PVSHAPE.exists())
print("COM_PV   :", cfg.COM_PV.exists())

print("\nPV Masters encontrados:")
for f in sorted(cfg.COM_PV.glob("*.dss")):
    print(" ", f)

print("="*70 + "\n")
###################################################################
#### FUNÇÕES

# Verifica os arquivos PV_Master existentes no diretório especificado
# e retorna um dicionario contendo o nome do arquivo e o respectivo nível
# de penetração.
def localizar_PV_Masters():

    PV_masters = []

    arquivos = sorted(
        cfg.COM_PV.glob("PV_Master*.dss")
    )

    for arquivo in arquivos:

        nome = arquivo.stem.replace(
            "PV_Master",
            ""
        )

        volt_var = nome.endswith("_VV")

        nome_nivel = (
            nome[:-3]
            if volt_var
            else nome
        )

        try:
            nivel = float(nome_nivel) / 100
        except ValueError:
            print(
                f"Ignorando Master com nome inválido: "
                f"{arquivo.name}"
            )
            continue

        if nivel <= 0:
            continue

        nome_geradores = (
            f"geradoresPV_{int(100*nivel)}"
            f"{'_VV' if volt_var else ''}.dss"
        )

        arquivo_geradores = cfg.COM_PV / nome_geradores

        if not arquivo_geradores.exists():
            print(
                f"\nAVISO: {arquivo.name} foi encontrado, "
                f"mas {nome_geradores} não existe."
            )
            continue

        PV_masters.append({
            "nome": nome_nivel,
            "nivel": nivel,
            "arquivo": arquivo,
            "arquivo_geradores": arquivo_geradores,
            "volt_var": volt_var
        })

    PV_masters.sort(
        key=lambda c: (
            c["nivel"],
            c["volt_var"]
        )
    )

    print("\nCenários encontrados:")

    for cenario in PV_masters:

        tipo = (
            "Volt-VAr"
            if cenario["volt_var"]
            else "FP = 1"
        )

        print(
            f"  {cenario['nome']}% | {tipo} | "
            f"{cenario['arquivo'].name} -> "
            f"{cenario['arquivo_geradores'].name}"
        )

    return PV_masters



############################################################
# COMPILA CIRCUITO
# Determina o número de dias a ser simulado
NUM_DIAS = "todos"  # ou a quantidade de dias desejada

if NUM_DIAS == "todos":

    HORAS = 8760

else:

    HORAS = int(NUM_DIAS) * 24


def compila_circuito(master_dss, arquivo_pv=None):

    dss.Basic.ClearAll()

    dss.Text.Command(
        f"compile {master_dss}"
    )

    # Carrega os LoadShapes de irradiancia e temperatura
    dss.Text.Command(
        f"redirect {cfg.PVSHAPE}"
    )

    if arquivo_pv is not None:

        dss.Text.Command(
            f"redirect {arquivo_pv}"
        )


############################################################
# CARREGA OS LOADSHAPES
def carregar_loadshapes():

    nomes_loadshapes = set(
        dss.LoadShape.AllNames()
    )

    dss.Loads.First()

    for _ in range(dss.Loads.Count()):

        nome_carga = (dss.Loads.Name())

        try:

            numero = (nome_carga.split("_")[1])

            nome_ls = (f"load_bus_{numero}")

            if nome_ls in nomes_loadshapes:

                dss.Loads.Yearly(nome_ls)

            else:

                print(
                    f"\nLoadShape "
                    f"{nome_ls} "
                    f"não encontrado."
                )

        except:
            
            pass

        dss.Loads.Next()

    print("\nOs LoadShapes foram carregados.")


############################################################
# CONFIGURAÇÕES DE SIMULAÇÃO
def configura_simulacao():

    # Simulação no modo anual (Yearly Mode)
    dss.Text.Command("set mode=yearly")

    # Passo de tempo da simulação (1 hora)
    dss.Text.Command("set stepsize=1h")

    # Executa um passo de tempo a cada comando Solve
    dss.Text.Command("set number=1")

    print("\nSimulação configurada.\n")

    
############################################################
# CARREGA A SÉRIE DO PVShape.dss
#
# A arquitetura atual usa exclusivamente:
#     cfg.PVSHAPE
#         -> .../dados/inputs/cenario_com_PV/PVShape.dss
#
# O vetor mult=(...) do próprio PVShape.dss é usado como a série
# normalizada correspondente à produção FV.
############################################################

def carregar_serie_pvshape():
    arquivo = cfg.PVSHAPE

    if not arquivo.exists():
        raise FileNotFoundError(
            f"PVShape não encontrado: {arquivo}"
        )

    texto_pvshape = arquivo.read_text(encoding="utf-8")

    match = re.search(
        r"\bmult\s*=\s*[\(\[]\s*(.*?)[\)\]]",
        texto_pvshape,
        re.IGNORECASE | re.DOTALL,
    )

    if not match:
        raise ValueError(
            "Não foi encontrado o vetor 'mult' dentro do "
            f"arquivo PVShape.dss: {arquivo}"
        )

    tokens = re.split(r"[\s,;]+", match.group(1).strip())

    valores = []
    for token in tokens:
        if not token:
            continue

        try:
            valores.append(float(token))
        except ValueError as exc:
            raise ValueError(
                f"Valor inválido no vetor mult do PVShape: {token!r}"
            ) from exc

    serie = np.asarray(valores, dtype=float)

    if len(serie) < HORAS:
        raise ValueError(
            f"O PVShape possui {len(serie)} valores, "
            f"mas a simulação requer {HORAS} horas."
        )

    if not np.all(np.isfinite(serie)):
        raise ValueError(
            "O vetor mult do PVShape contém NaN ou infinito."
        )

    if np.min(serie) < -1e-9 or np.max(serie) > 1.0 + 1e-9:
        raise ValueError(
            "O PVShape não está normalizado entre 0 e 1. "
            f"Min={np.min(serie):.6f}, Max={np.max(serie):.6f}"
        )

    print(f"\nPVShape utilizado: {arquivo}")
    print(f"Valores lidos do vetor mult: {len(serie)}")
    print(
        f"Min={np.min(serie):.6f} | "
        f"Max={np.max(serie):.6f}"
    )

    return serie


irradiancia = carregar_serie_pvshape()


############################################################
# TABELA ÚNICA DE FATORES DE POTÊNCIA DAS CARGAS
#
# Uma única realização por carga/hora.
# A mesma tabela é reutilizada em TODOS os cenários.
#
# Arquivo persistente:
#     cfg.OUT_PV / FP_cargas_aleatorio.xlsx
############################################################

ARQUIVO_FP_UNICO = cfg.OUT_PV / "FP_cargas_aleatorio.xlsx"


def gera_tabela_fp_unica(load_names, horas):
    """
    Gera ou carrega a única realização aleatória de FP.

    Se a tabela já existir e corresponder exatamente às cargas/horas
    atuais, ela será reutilizada.
    """

    ARQUIVO_FP_UNICO.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    nomes = [str(x) for x in load_names]

    # --------------------------------------------------------
    # Reutiliza uma tabela já existente
    # --------------------------------------------------------

    if ARQUIVO_FP_UNICO.exists():

        try:
            tabela = pd.read_excel(
                ARQUIVO_FP_UNICO,
                index_col=0,
            )

            tabela.columns = tabela.columns.astype(str)
            tabela.index = pd.to_numeric(
                tabela.index,
                errors="raise",
            ).astype(int)

            indice_esperado = np.arange(horas)

            if (
                len(tabela) == horas
                and list(tabela.columns) == nomes
                and np.array_equal(
                    tabela.index.to_numpy(dtype=int),
                    indice_esperado
                )
                and np.all(np.isfinite(tabela.to_numpy(dtype=float)))
                and np.all(
                    (tabela.to_numpy(dtype=float) >= 0.85)
                    & (tabela.to_numpy(dtype=float) <= 0.99)
                )
            ):
                print(
                    "\nTabela única de FP reutilizada:"
                    f"\n{ARQUIVO_FP_UNICO}"
                )
                return tabela

        except Exception as exc:
            print(
                "\nNão foi possível reutilizar a tabela de FP existente."
                f"\nMotivo: {exc}"
            )

        print(
            "\nA tabela de FP existente não corresponde à configuração atual."
            "\nUma nova realização será gerada."
        )

    # --------------------------------------------------------
    # Gera uma única realização
    # --------------------------------------------------------

    tabela = pd.DataFrame(
        index=np.arange(horas),
        columns=nomes,
        dtype=float,
    )

    for load in nomes:

        fp_base = np.random.normal(
            0.92,
            0.02,
        )

        fp_min = max(
            0.85,
            fp_base - 0.05,
        )

        fp_max = min(
            0.99,
            fp_base + 0.05,
        )

        tabela[load] = np.random.uniform(
            fp_min,
            fp_max,
            horas,
        )

        # Segurança numérica: mantém todos os valores no intervalo físico adotado.
        tabela[load] = tabela[load].clip(0.85, 0.99)

    tabela.index.name = "hora"

    tabela.to_excel(
        ARQUIVO_FP_UNICO
    )

    print(
        "\nTabela única de FP das cargas gerada e salva em:"
        f"\n{ARQUIVO_FP_UNICO}"
    )

    return tabela


############################################################
# SIMULA CENÁRIO
def simula_cenario(
        nome_cenario,
        arquivo_pv=None,
        volt_var=False
        ):

    tipo = "Volt-VAr" if volt_var else "FP = 1"

    print(
        f"\nSimulando cenário com "
        f"{nome_cenario}% de penetração PV ({tipo})"
    )

    compila_circuito(
        cfg.MASTER_BL,
        arquivo_pv
    )


    carregar_loadshapes()

    configura_simulacao()

    # Inicializa arrays numpy para salvar resultados
    potencia_kw = np.zeros(HORAS)

    potencia_kvar = np.zeros(HORAS)

    fp_subestacao = np.zeros(HORAS)

    tensao_min = np.zeros(HORAS)

    tensao_max = np.zeros(HORAS)

    potencia_pv = np.zeros(HORAS)


    # ======================================================
    # FATORES DE POTÊNCIA DAS CARGAS
    #
    # Uma única realização é reutilizada em TODOS os cenários.
    # ======================================================

    load_names = sorted(
        str(nome) for nome in dss.Loads.AllNames()
    )

    tabela_fp = gera_tabela_fp_unica(
        load_names,
        HORAS,
    )

    for h in range(HORAS):

        # Atualiza o FP de cada carga usando a mesma tabela.
        for load in load_names:

            dss.Loads.Name(load)

            fp = float(
                tabela_fp.loc[h, str(load)]
            )

            dss.Loads.PF(fp)

        # Avança uma hora
        dss.Text.Command(f"set hour={h}")

        dss.Text.Command("solve")

        if not dss.Solution.Converged():

            print(
                f"\nA simulação não convergiu "
                f"na hora {h}"
                )

            continue

        # Potência subestação
        # Obs.: para OpenDSS:
        #           consumo de potência  -> valores negativos
        #           injeção de potência  -> valores positivos
        p_total, q_total = (dss.Circuit.TotalPower())

        P = -p_total

        Q = -q_total

        potencia_kw[h] = P

        potencia_kvar[h] = Q

        # Calcula o fator de potência
        S = np.sqrt(P**2 + Q**2)

        if S == 0:

            fp_subestacao[h] = 0

        else:

            fp_subestacao[h] = P / S

    
        # Tensões
        tensoes = np.array(dss.Circuit.AllBusMagPu())

        tensao_min[h] = np.min(tensoes)

        tensao_max[h] = np.max(tensoes)

        # Potência PV total
        p_pv = 0

        if len(dss.PVsystems.AllNames()) > 0:

            for pv in dss.PVsystems.AllNames():

                dss.PVsystems.Name(pv)

                p_pv += (dss.PVsystems.kW())

        potencia_pv[h] = p_pv

        # Exibe os resultados a cada 1000 horas
        if h % 1000 == 0:

            print(

                f"{h:4d} "

                f"P={P:.1f} "

                f"Q={Q:.1f} "

                f"PV={p_pv:.1f}"

            )
    # Salva os resultados em um dataframe
    df = pd.DataFrame({

        "hora":
            np.arange(HORAS),

        "Irradiancia_pu":
            irradiancia[:HORAS],

        "P_kW":
            potencia_kw,

        "Q_kvar":
            potencia_kvar,

        "FP":
            fp_subestacao,

        "Vmin":
            tensao_min,

        "Vmax":
            tensao_max,

        "P_PV":
            potencia_pv
    })

    return df


########################################################
# SALVA RESULTADOS
def salva_resultados(
        df,
        cenario
        ):

    nome_cenario = cenario["nome"]
    sufixo = "_VV" if cenario.get("volt_var", False) else ""
        
    # Arquivo .parquet
    df.to_parquet(
        cfg.OUT_PV /
        f"resultados{nome_cenario}{sufixo}.parquet",
        index=False
        )

    # Arquivo .csv
    df.to_csv(
        cfg.OUT_PV /
        f"resultados{nome_cenario}{sufixo}.csv",
        sep=";",
        decimal=",",
        index=False
        )

    # Arquivo .xlsx
    df.to_excel(
        cfg.OUT_PV /
        f"resultados{nome_cenario}{sufixo}.xlsx",
        index=False
        )
    
    print(
        f"\nResultados salvos em "
        f"{cfg.OUT_PV}"
    )

    print("_"*60)

# Salva um relatorio
def salva_relatorio(
        df,
        nome_cenario,
        cenario=None
    ):

    sufixo = "_VV" if cenario and cenario.get("volt_var", False) else ""

    arquivo_resumo = (
        cfg.OUT_PV /
        f"relatorio{nome_cenario}{sufixo}.xlsx"
    )

    resumo = pd.DataFrame({

        "Pmax_kW":
            [df["P_kW"].max()],

        "Pmin_kW":
            [df["P_kW"].min()],

        "Pmedio_kW":
            [df["P_kW"].mean()],

        "Qmedio_kvar":
            [df["Q_kvar"].mean()],

        "FPmedio":
            [df["FP"].mean()],

        "Vmin":
            [df["Vmin"].min()],

        "Vmax":
            [df["Vmax"].max()],

        "Energia_PV_kWh":
            [df["P_PV"].sum()]
    })

    resumo.to_excel(
        arquivo_resumo,
        index=False
        )


# EXPORTAÇÃO COMPLETA


def exporta_resultados(

        df,

        nome_cenario

):

    salva_resultados(

        df,

        nome_cenario

    )

    salva_relatorio(

        df,

        nome_cenario,

        cenario

    )


############################################################
# PLOTAGENS

# Gráfico 1 - Potências ativa e reativa
def plotar_potencias(df, cenario):

    pasta = cfg.FIGS_PV
    
    nivel = cenario["nivel"]
    sufixo = "_VV" if cenario.get("volt_var", False) else ""

    plt.figure(figsize=(12,5))

    # Potência ativa
    plt.plot(
        df["hora"],
        df["P_kW"],
        color="tab:blue",
        linewidth=1.2,
        label="Potência ativa"
    )

    # Potência reativa
    plt.plot(
        df["hora"],
        df["Q_kvar"],
        color="tab:red",
        linewidth=1.0,
        label="Potência reativa"
    )

    plt.title(
        f"Potências na subestação - Cenário com {nivel*100}% de PV"
    )

    plt.xlabel("Hora")

    plt.ylabel("Potência (kW / kvar)")

    plt.grid(
        True,
        linestyle="--",
        alpha=0.4
    )

    plt.legend()
    plt.tight_layout()
    plt.savefig(
        pasta /
        f"Potencias_{nivel}{sufixo}.png",
        dpi=300
        )

    plt.show()
    plt.close()
    
############################################################
# PLOT FATOR DE POTÊNCIA
############################################################

def plota_fp(df, cenario):

    pasta = cfg.FIGS_PV
    nivel = cenario["nivel"]
    sufixo = "_VV" if cenario.get("volt_var", False) else ""
    # Cria uma nova figura
    plt.figure(

        figsize=(12,5)

    )

    # ======================================================
    # Curva do fator de potência

    plt.plot(

        df["hora"],

        df["FP"],

        color="tab:green",      # cor da curva

        linewidth=1.2,          # espessura da linha

        label="Fator de potência"

    )

    # ======================================================

    # Título do gráfico
    plt.title(

        f"Fator de potência da subestação - Cenário {nivel*100}"

    )

    # Nome do eixo x
    plt.xlabel(

        "Hora do ano"

    )

    # Nome do eixo y
    plt.ylabel(

        "Fator de potência"

    )

    # Limites do eixo y
    plt.ylim(

        0.80,

        1.00

    )

    # Ativa a grade
    plt.grid(

        True,

        linestyle="--",

        alpha=0.4

    )

    # Exibe a legenda
    plt.legend()

    # Ajusta automaticamente os espaçamentos
    plt.tight_layout()

    # Salva a figura
    plt.savefig(

        pasta /

        f"FP_{nivel*100}{sufixo}.png",

        dpi=300

    )

    plt.show()
    # Fecha a figura
    plt.close()
    
############################################################
# PLOT NÍVEIS DE TENSÃO
############################################################

def plota_tensao(df, cenario):

    pasta = cfg.FIGS_PV
    nivel = cenario["nivel"]
    sufixo = "_VV" if cenario.get("volt_var", False) else ""
    # Cria uma nova figura
    plt.figure(

        figsize=(12,5)

    )

    # ======================================================
    # Tensão mínima

    plt.plot(

        df["hora"],

        df["Vmin"],

        color="tab:red",

        linewidth=1.2,

        label="Tensão mínima"

    )

    # ======================================================
    # Tensão máxima

    plt.plot(

        df["hora"],

        df["Vmax"],

        color="tab:blue",

        linewidth=1.2,

        label="Tensão máxima"

    )

   

    # Título do gráfico
    plt.title(

        f"Níveis de tensão - Cenário {nivel}"

    )

    # Nome do eixo x
    plt.xlabel(

        "Hora do ano"

    )

    # Nome do eixo y
    plt.ylabel(

        "Tensão (pu)"

    )



    # Ativa a grade
    plt.grid(

        True,

        linestyle="--",

        alpha=0.4

    )

    # Exibe a legenda
    plt.legend()

    # Ajusta automaticamente os espaçamentos
    plt.tight_layout()

    # Salva a figura
    plt.savefig(

        pasta /

        f"Tensoes_{nivel}{sufixo}.png",

        dpi=300

    )

    plt.show()
    # Fecha a figura
    plt.close()
    
def plota_comparativo_potencia(resultados):

    pasta = cfg.FIGS_PV
    

    plt.figure(

        figsize=(14,6)

    )

    # ======================================================
    # Plota todos os cenários

    for nivel in sorted(resultados.keys(), reverse=True):

        df = resultados[nivel]



        # Destaca o caso base
        print(nivel)
        if nivel == 0.0:

            plt.plot(

                df["hora"],

                df["P_kW"],

                #color="black",

                linewidth=0.5,

                label="Base",
                alpha = 0.5

            )

        else:

            plt.plot(

                df["hora"],

                df["P_kW"],

                linewidth=0.8,

                label=f"{nivel}%",
#                alpha = 0.75

            )

    # ======================================================
    # Linha indicando potência nula

    plt.axhline(

        y=0,

        color="black",

        linewidth=0.8

    )

    # ======================================================

    plt.title(

        "Potência ativa na subestação"

    )

    plt.xlabel(

        "Hora do ano"

    )

    plt.ylabel(

        "Potência ativa (kW)"

    )

    plt.grid(

        True,

        linestyle="--",

        alpha=0.4

    )

    plt.legend(

        title="Penetração FV"

    )

    plt.tight_layout()

    plt.savefig(

        pasta /

        "Comparativo_Potencia_Ativa.png",

        dpi=300

    )

    plt.show()
    plt.close()
############################################################
# COMPARAÇÃO DAS POTÊNCIAS REATIVAS
############################################################

def plota_comparativo_potencia_reativa(resultados):

    pasta = cfg.FIGS_PV

    # Cria uma nova figura
    plt.figure(

        figsize=(14,6)

    )

    # ======================================================
    # Plota todos os cenários

    for nivel, df in resultados.items():


        if nivel == 0.0:

            plt.plot(

                df["hora"],

                df["Q_kvar"],

                color="black",

                linewidth=2.5,

                label="Base"

            )

        else:

            plt.plot(

                df["hora"],

                df["Q_kvar"],

                linewidth=1.2,

                label=f"{nivel}%"

            )

    # ======================================================
    # Linha indicando potência nula

    plt.axhline(

        y=0,

        color="black",

        linewidth=0.8

    )

    # ======================================================

    # Título do gráfico
    plt.title(

        "Potência reativa na subestação"

    )

    # Nome do eixo x
    plt.xlabel(

        "Hora do ano"

    )

    # Nome do eixo y
    plt.ylabel(

        "Potência reativa (kvar)"

    )

    # Ativa a grade
    plt.grid(

        True,

        linestyle="--",

        alpha=0.4

    )

    # Exibe a legenda
    plt.legend(

        title="Penetração FV"

    )

    # Ajusta automaticamente os espaçamentos
    plt.tight_layout()

    # Salva a figura
    plt.savefig(

        pasta /

        "Comparativo_Potencia_Reativa.png",

        dpi=300

    )

    plt.show()
    plt.close()
    
def plota_maior_geracao_PV2(resultados):

    pasta = cfg.FIGS_PV

    # Caso base
    df_base = resultados[0.0]

    # Para cada cenário com PV
    for nivel, df_pv in sorted(resultados.items()):

        if nivel == 0.0:
            continue

        # ======================================================
        # Energia FV produzida em cada dia

        energia_fv_diaria = (

            df_pv.groupby(

                df_pv["hora"] // 24

            )["P_PV"].sum()

        )

        # Dia de maior geração FV

        dia_maior_geracao = energia_fv_diaria.idxmax()

        hora_inicial = dia_maior_geracao * 24

        hora_final = hora_inicial + 24

        # ======================================================
        # Seleciona somente as 24 horas do dia

        base = df_base.iloc[hora_inicial:hora_final]

        pv = df_pv.iloc[hora_inicial:hora_final]

        horas = np.arange(24)

        # ======================================================
        plt.figure(figsize=(12,5))

        plt.plot(
            horas,
            base["P_kW"],
            color="black",
            linewidth=2.5,
            label="Base"
        )

        plt.plot(
            horas,
            pv["P_kW"],
            linewidth=2,
            label=f"{nivel*100:.0f}% PV"
        )

        plt.fill_between(
            horas,
            base["P_kW"],
            pv["P_kW"],
            alpha=0.30,
            label="Redução da demanda"
        )

        plt.title(
            f"Maior geração FV - {nivel*100:.0f}%"
        )

        plt.xlabel("Hora do dia")
        plt.ylabel("Potência ativa (kW)")
        plt.xticks(np.arange(0,24,2))

        plt.grid(
            True,
            linestyle="--",
            alpha=0.4
        )

        plt.legend()

        plt.tight_layout()

        plt.savefig(
            pasta /
            f"Maior_Geracao_FV_{int(nivel*100):02d}.png",
            dpi=300
        )

        plt.show()
        plt.close()    
#plota_comparativo_potencia(resultado)
#plota_comparativo_potencia_reativa(resultado)

############################################################
# COMPARAÇÃO DO DIA DE MAIOR GERAÇÃO FV
############################################################

def plota_maior_geracao_PV(resultados):

    pasta = cfg.FIGS_PV

    # ======================================================
    # Caso base

    df_base = resultados[0.0]

    # ======================================================
    # Identifica o cenário de maior penetração

    maior_nivel = max(resultados.keys())

    df_maior = resultados[maior_nivel]

    # ======================================================
    # Descobre o dia de maior geração FV

    energia_diaria = (

        df_maior.groupby(

            df_maior["hora"] // 24

        )["P_PV"].sum()

    )

    dia_maior = energia_diaria.idxmax()

    hora_inicial = dia_maior * 24

    hora_final = hora_inicial + 24

    horas = np.arange(24)

    # ======================================================
    # Cria figura

    plt.figure(figsize=(12,5))

    # ======================================================
    # Base

    base = df_base.iloc[hora_inicial:hora_final]

    plt.plot(

        horas,

        base["P_kW"],

        color="black",

        linewidth=2.8,

        label="Base",

        zorder=10

    )

    # ======================================================
    # Demais cenários

    for nivel, df in sorted(resultados.items()):

        if nivel == 0.0:
            continue

        dia = df.iloc[hora_inicial:hora_final]

        plt.plot(

            horas,

            dia["P_kW"],

            linewidth=1.5,

            alpha=0.9,

            label=f"{nivel*100:.0f}%"

        )

    # ======================================================

    plt.title(

        f"Perfil diário no dia de maior geração fotovoltaica (Dia {dia_maior+1})"

    )

    plt.xlabel(

        "Hora do dia"

    )

    plt.ylabel(

        "Potência ativa (kW)"

    )

    plt.xticks(

        np.arange(0,24,2)

    )

    plt.grid(

        True,

        linestyle="--",

        alpha=0.4

    )

    plt.legend(

        title="Penetração FV"

    )

    plt.tight_layout()

    plt.savefig(

        pasta /

        "Maior_Geracao_FV_Comparativo.png",

        dpi=300

    )

    plt.show()

    plt.close()

##################################################################
# FUNÇÃO PRINCIPAL
def main():

    lista_PV_masters = localizar_PV_Masters()

    resultados_normais = {}
    resultados_vv = {}

    # ======================================================
    # CASO BASE
    # ======================================================

    cenario_base = {
        "nome": "0",
        "nivel": 0.0,
        "arquivo": None,
        "volt_var": False
    }

    resultados_base = simula_cenario(
        "0",
        None,
        False
    )

    salva_resultados(
        resultados_base,
        cenario_base
    )

    salva_relatorio(
        resultados_base,
        "0",
        cenario_base
    )

    plotar_potencias(
        resultados_base,
        cenario_base
    )

    plota_fp(
        resultados_base,
        cenario_base
    )

    plota_tensao(
        resultados_base,
        cenario_base
    )

    resultados_normais[0.0] = resultados_base

    # ======================================================
    # CENÁRIOS PV
    # ======================================================

    for cenario in lista_PV_masters:

        nome_cenario = cenario["nome"]
        arquivo_pv = cenario["arquivo"]
        nivel = cenario["nivel"]
        volt_var = cenario["volt_var"]

        resultados = simula_cenario(
            nome_cenario,
            arquivo_pv,
            volt_var
        )

        salva_resultados(
            resultados,
            cenario
        )

        salva_relatorio(
            resultados,
            nome_cenario,
            cenario
        )

        plotar_potencias(
            resultados,
            cenario
        )

        plota_fp(
            resultados,
            cenario
        )

        plota_tensao(
            resultados,
            cenario
        )

        if volt_var:
            resultados_vv[nivel] = resultados
        else:
            resultados_normais[nivel] = resultados

    # ======================================================
    # COMPARAÇÕES DOS CENÁRIOS FP=1
    # ======================================================

    if len(resultados_normais) > 1:

        plota_comparativo_potencia(
            resultados_normais
        )

        plota_comparativo_potencia_reativa(
            resultados_normais
        )

        plota_maior_geracao_PV2(
            resultados_normais
        )

        plota_maior_geracao_PV(
            resultados_normais
        )

    # ======================================================
    # COMPARAÇÃO FP=1 x VOLT-VAR
    # ======================================================

    comparacao = []

    for nivel in sorted(resultados_vv):

        if nivel not in resultados_normais:
            continue

        df_fp1 = resultados_normais[nivel]
        df_vv = resultados_vv[nivel]

        comparacao.append({
            "Penetracao": 100 * nivel,
            "Pmedio_FP1_kW": df_fp1["P_kW"].mean(),
            "Pmedio_VV_kW": df_vv["P_kW"].mean(),
            "Qmedio_FP1_kvar": df_fp1["Q_kvar"].mean(),
            "Qmedio_VV_kvar": df_vv["Q_kvar"].mean(),
            "FPmedio_FP1": df_fp1["FP"].mean(),
            "FPmedio_VV": df_vv["FP"].mean(),
            "Vmin_FP1": df_fp1["Vmin"].min(),
            "Vmin_VV": df_vv["Vmin"].min(),
            "Vmax_FP1": df_fp1["Vmax"].max(),
            "Vmax_VV": df_vv["Vmax"].max(),
            "Energia_PV_FP1_kWh": df_fp1["P_PV"].sum(),
            "Energia_PV_VV_kWh": df_vv["P_PV"].sum()
        })

    if comparacao:

        df_comparacao = pd.DataFrame(
            comparacao
        )

        arquivo_comparacao = (
            cfg.OUT_PV /
            "Comparacao_FP1_vs_VoltVar.xlsx"
        )

        df_comparacao.to_excel(
            arquivo_comparacao,
            index=False
        )

        print(
            "\nComparação FP=1 x Volt-VAr salva em:"
            f"\n{arquivo_comparacao}"
        )

    end_timer = time.perf_counter()

    tempo_execucao = calc_tempo(
        begin_timer,
        end_timer
    )

    print("\nSimulações concluídas")
    print(f"\nTempo de execução: {tempo_execucao}")

    return {
        "normal": resultados_normais,
        "volt_var": resultados_vv
    }


resultado = main()


