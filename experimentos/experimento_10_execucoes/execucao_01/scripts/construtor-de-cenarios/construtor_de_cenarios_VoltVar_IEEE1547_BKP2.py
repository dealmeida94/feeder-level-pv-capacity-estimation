#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
O script gera diferentes cenários de penetração de PV, a partir dos loadshapes
declarados na simulação de base (sem PV).

A potência total de geração PV inserida na é determinada por uma lista
contendo os percentuais em forma decimal. Ex.: [0.2, 0.3, 0.4]

A potência individual de cada geração PV é determinada por uma lista de valores
possíveis. A seleção pode ocorrer de maneira aleatória, mas podem também ser fornecida
uma lista de pesos, aumentando a probabilidade de seleção de uma potência PV específica.

A potência PV instalada em cada bus é limitada a um percentual máximo da potência do bus,
para evitar concentrações excessivas de geração.

O processo consiste nas seguintes etapas:
    
    1. Leitura do baseload e calculo da carga média diurna no barramento da
    subestação.Leitura da curva de potência ativa do barramento da subestação, sem PV.
    
    2. Determina a potência PV total (Potência alvo) a ser inserida;
    
    3. Leitura dos arquivos Loadshapes.dss para coletar
    dados dos bus (identificador e carga).
    
    4. Realiza a inserção dos PVs
         4.1 - Gera uma população de PVs com base em uma lista de potências individuais
               possíveis de serem atribuídas aos PVs
               Permite incluir uma lista de pesos, os quais determinam a probabilidade de ocorrência
               de uma determinada potência PV. Se for desejado que todos as potências da lista
               tenham a mesma possibilidade de ocorrência, os pesos devem ser todos iguais a 1

         4.2 - Ordena a população PV em ordem decrescente de potência
         
         4.3 - Distribuia a população PV entre os buses
               respeitando o limite máximo de penetração PV.
               
         4.4 - Gera relatório

    5. Constroi os arquivos 'geradoresPV_XX.dss' contendo os geradores PV distribuidos.
         5.1 - Verifica o número de bases do bus para a correta parametrização do PV
        
         5.2 - Cria os arquivo .dss contendo a definição de todos os PVs do cenário de analisado.
         O PV é inserido na rede através do comando "New PVSystem" com seus respectivos parâmetros:
         nome, bus de conexão, número de fases, potência instalada e PVShape calculado pelo PVWatts.
        
         5.3 - Gera o arquivo Master.dss com o "Redirect" para o arquivo de .dss que contém
         os PVSystems do cenário simulado.
        
         5.4 - Funções para plotagens
        
    6. Outras plotagens. Plota curvas baseload (carga média diurna) e níveis PV 

    
ENTRADAS:
    + Lista contendo os percentuais de penetração PV desejado
    + Resultados da simulação base {resultados_sem_PV.parquet}
    + Arquivos Loadshapes.dss {Loadshapes_FeederA,
                               Loadshapes_FeederB,
                               Loadshapes_FeederC}
    
SAÍDAS:
    + Para cada cenário:
        geradoresPV_XX.dss
        geradoresPV_XX_VV.dss
        geradoresPV_XX.xlsx
        PV_MasterXX.dss
        PV_MasterXX_VV.dss
        (XX é o nível de penetração)
        
    + Relatório de processamento log_contrucao_cenarios.txt

"""

import sys
import random
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(ROOT))

import configs as cfg

# Modelo FV PVWatts
from pvwatts import gera_pvshape


############################################################
# PARÂMETROS DO CENÁRIO DE DISTRIBUIÇÃO DOS PVs
#
# Limite máximo da potência FV instalada em cada bus, em relação
# à carga nominal daquele bus.
# Ex.: 0.40 = no máximo 40% da carga do bus.
#
# Para os cenários com Volt-VAr, um limite menor tende a reduzir
# a concentração de geração e, consequentemente, a possibilidade
# de variações de tensão excessivas.
MAX_PV_PERCENT_LOAD_BUS = 0.40

# Estratégia de distribuição:
# "BALANCEADA" -> prioriza buses com menor penetração PV acumulada.
# "ALEATORIA"  -> mantém o sorteio aleatório original.
ESTRATEGIA_DISTRIBUICAO_PV = "BALANCEADA"

############################################################
##########  DECLARAÇÃO DE FUNÇÕES ##########################

# Etapa 1 - Leitura do baseload e calculo da carga
# média diurna no barramento da subestação.
def calcula_media_diurna(
        caminho_parquet_baseload # caminho para o arquivo parquet que
        ):                       # contém os resultados da simulação sem PV

    df = pd.read_parquet(caminho_parquet_baseload)
    
    # Verifica se existe a coluna P_kW
    if "P_kW" not in df.columns:
        print("Coluna P_kW não encontrada.")

    # Desconsidera o sinal +/-
    df["P_kW"] = (df["P_kW"].abs())

    # Para cada hora, calcula a carga média
    curva_media = (df.groupby("hora")["P_kW"].mean())

    # Seleciona apenas as médias entre 6 e 18 horas
    curva_media = curva_media[
        (curva_media.index >= 6)
        &
        (curva_media.index <= 18)
    ]

    # Calcula a curva média no período considerado
    carga_media = curva_media.mean()

    print(
        f"\nCarga média diurna sem PV = "
        f"{carga_media:.2f} kW"
    )

    return (carga_media, curva_media)

# Etapa 2 - Determina a potência PV total (Potência alvo) a ser inserida
def calcula_potencia_PV_alvo(
        carga_media,  # carga média diurna
        penetracao_PV # percentual de penetração PV desejado, forma decimal.
        ):

    alvos_PV = []

    for p in penetracao_PV:

        geracaoPV = carga_media * p

        alvos_PV.append(geracaoPV)

    return alvos_PV

# Etapa 3 - Leitura dos arquivos Loadshapes.dss para coletar
# dados dos bus (identificador e carga)

def salvar_potencias_cenarios(
        niveis_PV,
        potencias_PV
        ):

    print("\nSalvando potências dos cenários\n")

    df = pd.DataFrame({

        "cenario": [
            int(100 * nivel)
            for nivel in niveis_PV
        ],

        "potencia_PV_kW": potencias_PV

    })

    arquivo = (
        cfg.LOGS_DIR /
        "Potencias_Cenarios.xlsx"
    )

    df.to_excel(
        arquivo,
        index=False
    )

    print(
        f"Arquivo salvo: {arquivo.name}"
    )
    
    
def buscar_dados_buses(
        caminho_loadshapes # caminho para arquivos loadshapes
        ):

    dados_buses = []

    for loadshapes in caminho_loadshapes:
        with open(loadshapes, "r") as f:
            for linha in f:
                linha = linha.lower()
                if (
                    "bus1=" in linha
                    and
                    "kw=" in linha
                ):
                    try:
                        bus = (
                            linha
                            .split("bus1=")[1]
                            .split()[0]
                        )

                        kw = abs(
                            float(
                                linha
                                .split("kw=")[1]
                                .split()[0]
                            )
                        )

                        dados_buses.append({
                            "bus": bus,
                            "kw": kw
                        })

                    except:
                        continue

    print(
        f"\nArquivos Loadshapes.dss foram lidos e"
        f" todos os loads foram encontradas."
        f"\nTotal: {len(dados_buses)} nós"
    )

    return dados_buses

# Etapa 4 - Realiza a inserção dos PVs
# 4.1 - Gera uma população de PVs com base em uma lista de potências individuais
# possíveis de serem atribuídas aos PVs
# A permite incluir uma lista de pesos, os quais determinam a probabilidade de ocorrência
# de uma determinada potência PV. Se for desejado que todos as potências da lista
# tenham a mesma possibilidade de ocorrência, os pesos devem ser todos iguais a 1
def gera_populacao_PVs(
        potencia_alvo, # Potência total da população PV a ser criada
        tolerancia=5 # Tolerância para +/- da potência alvo
        ):
    
    # Lista contendo as potências em kW atribuíveis aos PVs individualmente
    potencias = [
        2.0,
        3.0,
        4.0,
        5.0,
        7.5,
        10.0
    ]

    # Possibilita determinar a probabilidade de ocorrência de cada sistema
    # PV.Sistemas com maior peso têm maior chance de serem sorteados
    # durante a geração da população de PVs.
    #
    # A probabilidade é dada por:
    # P = peso / soma(pesos)
    pesos = [
        1,
        1,
        1,
        1,
        1,
        1,
    ]

    populacao_PV = []

    potencia_total = 0.0

    contador = 1

    while True:

        restante = potencia_alvo - potencia_total

        # Critério de parada
        if abs(restante) <= tolerancia:
            break

        candidatos = []
        pesos_candidatos = []

        for i, potencia in enumerate(potencias):

            if potencia_total + potencia <= potencia_alvo + tolerancia:

                candidatos.append(potencia)
                pesos_candidatos.append(pesos[i])

        if len(candidatos) == 0:
            break

        potencia = random.choices(
            candidatos,
            weights=pesos_candidatos,
            k=1
        )[0]

        populacao_PV.append({
            "nome":
                f"PV_{contador}",
                
            "potencia":
                potencia
        })

        potencia_total += potencia

        contador += 1

 
    print(
        f"Potência alvo              : {potencia_alvo:.2f} kW"
    )

    print(
        f"Potência inserida         : {potencia_total:.2f}({100*potencia_total/potencia_alvo:.2f}%) kW"
    )

    print(
        f"Erro (Alvo - Inserido)    : {potencia_total-potencia_alvo:+.2f} kW"
    )

    print(
        f"Quantidade de PVs         : {len(populacao_PV)}"
    )

    print(
        f"Potência PV média         : {potencia_total/len(populacao_PV):.2f} kW"
    )

    return populacao_PV

# Etapa 4.2 - Ordena a população PV em ordem decrescente de potência
def ordenar_populacao_PVs(populacao):

    populacao.sort(
        key=lambda pv: pv["potencia"],
        reverse=True
    )

    populacao_ordenada = populacao
    
    print(
        f"Maior PV : {populacao_ordenada[0]['potencia']:.2f} kW"
    )

    print(
        f"Menor PV : {populacao_ordenada[-1]['potencia']:.2f} kW"
    )

    return populacao_ordenada

# Etapa 4.3 - Distribui a a população PV entre os buses
# respeitando o limite máximo de penetração PV.
def distribuir_PVs(
        dados_bus,  # dados dos buses
        populacao_PV,   # população PV a ser inserida
        max_pot_PV=MAX_PV_PERCENT_LOAD_BUS,
        estrategia=ESTRATEGIA_DISTRIBUICAO_PV
        ):

    # Máxima penetração PV no bus.
    # O valor é passado como parâmetro para que possa ser alterado
    # facilmente no início do script ou na chamada da função.
    if not 0 < max_pot_PV <= 1:
        raise ValueError(
            "max_pot_PV deve estar entre 0 e 1. "
            "Ex.: 0.40 para limitar a 40% da carga do bus."
        )

    estrategia = estrategia.upper()
    if estrategia not in ("BALANCEADA", "ALEATORIA"):
        raise ValueError(
            "estrategia deve ser 'BALANCEADA' ou 'ALEATORIA'."
        )
    
    # Estado atual do bus
    estado_buses = []

    for bus in dados_bus:

        estado_buses.append({

            "bus": bus["bus"],

            "kw": bus["kw"],

            "pv_instalado": 0.0,

            "numero_pvs": 0

        })

    distribuicao = []

    for PV in populacao_PV:

        potencia = PV["potencia"]

        # Buses com capacidade de receber o PV
        elegiveis = []
        
        for bus in estado_buses:

            limite = max_pot_PV * bus["kw"]

            if bus["pv_instalado"] + potencia <= limite:

                elegiveis.append(bus)

        if len(elegiveis) == 0:

            print(
                f"Não foi possível alocar o "
                f"{PV['nome']} "
                f"({potencia:.1f} kW) "
            )
            
            continue

        # ----------------------------------------------------------
        # Seleção do barramento
        # ----------------------------------------------------------
        # A estratégia BALANCEADA evita que o sorteio aleatório
        # concentre vários PVs nos mesmos buses. Entre os buses
        # elegíveis, prioriza aquele com menor penetração PV atual.
        # Em caso de empate, sorteia entre os candidatos.
        if estrategia == "BALANCEADA":
            menores_penetracoes = []

            for candidato in elegiveis:
                if candidato["kw"] > 0:
                    penetracao_atual = (
                        candidato["pv_instalado"] /
                        candidato["kw"]
                    )
                else:
                    penetracao_atual = float("inf")

                menores_penetracoes.append(penetracao_atual)

            menor_penetracao = min(menores_penetracoes)

            candidatos_menor_penetracao = [
                candidato
                for candidato, penetracao_atual in zip(
                    elegiveis,
                    menores_penetracoes
                )
                if np.isclose(
                    penetracao_atual,
                    menor_penetracao,
                    rtol=0,
                    atol=1e-12
                )
            ]

            bus = random.choice(candidatos_menor_penetracao)

        else:
            # Estratégia original: sorteio aleatório entre os
            # barramentos elegíveis.
            bus = random.choice(elegiveis)

        # Atualiza estado do barramento
        bus["pv_instalado"] += potencia

        bus["numero_pvs"] += 1

        # Registra distribuição
        distribuicao.append({
            "nome":
                PV["nome"],

            "bus":
                bus["bus"],

            "potencia":
                potencia
        })

  
    potencia_solicitada = sum(
        pv["potencia"] for pv in populacao_PV
    )
    potencia_distribuida = sum(
        pv["potencia"] for pv in distribuicao
    )

    if potencia_distribuida < potencia_solicitada:
        print(
            "\nATENÇÃO: nem toda a potência da população PV foi "
            "alocada."
        )
        print(
            f"  Solicitada : {potencia_solicitada:.2f} kW"
        )
        print(
            f"  Distribuída: {potencia_distribuida:.2f} kW"
        )
        print(
            f"  Não alocada: "
            f"{potencia_solicitada - potencia_distribuida:.2f} kW"
        )
        print(
            "  Considere aumentar MAX_PV_PERCENT_LOAD_BUS ou "
            "rever a população de PVs."
        )

    return distribuicao, estado_buses

# Etapa 4.4 - Gera relatório
def gera_relatorio_PVs(estado_buses):

    resumo = []

    for bus in estado_buses:

        if bus["kw"] > 0:

            penetracao = (
                100 *
                bus["pv_instalado"] /
                bus["kw"]
            )

        else:

            penetracao = 0

        resumo.append({
            "bus":
                bus["bus"],

            "Carga_kW":
                bus["kw"],

            "PV_kW":
                round(
                    bus["pv_instalado"],
                    2
                ),

            "Penetracao":
                round(
                    penetracao,
                    2
                ),

            "Numero_PVs":
                bus["numero_pvs"]
        })

    df = pd.DataFrame(resumo)

    return df

# Função principal da Etapa 4
def GERA_POPULACAO_PVs(
        dados_bus,    # dados dos buses
        niveis_PV,    # níveis de penetração PV desejados
        potencias_PV  # lista com as potências de geradores PV possíveis
        ):            # de serem inseridos 

    cenarios = {}

    for nivel, potencia in zip(niveis_PV, potencias_PV):

        print(
            f"\nCENÁRIO COM {nivel*100:.2f} % DE PENETRAÇÃO"
        )
        
        # Etapa 4.1
        populacao = gera_populacao_PVs(
            potencia
            )

        # Etapa 4.2
        populacao = ordenar_populacao_PVs(
            populacao
            )

        # Etapa 4.3
        distribuicao, estado_buses = (
            distribuir_PVs(
                dados_bus,
                populacao,
                max_pot_PV=MAX_PV_PERCENT_LOAD_BUS,
                estrategia=ESTRATEGIA_DISTRIBUICAO_PV
                )
            )
        
        # Etapa 4.4
        resumo = gera_relatorio_PVs(
            estado_buses
        )

        cenarios[potencia] = {
            "distribuicao": distribuicao,
            "resumo": resumo
            }

    return cenarios

# Etapa 5 - Constroi os arquivos .dss
# 5.1 - Gera a curva temporal de geração FV com PVWatts
def gera_pvshape_pvwatts():
    """
    Gera o PVShape a partir dos dados climáticos processados.

    Arquitetura adotada:
        irradiância + temperatura
                    ↓
                PVWatts
                    ↓
             potência AC
                    ↓
              PVShape [pu]

    O PVShape é uma curva normalizada comum a todos os PVSystems.
    A potência nominal de cada PV é definida individualmente por
    kVA/Pmpp no arquivo do cenário.

    O OpenDSS recebe somente o PVShape. Não é utilizado Tdaily/TempShape.
    """

    # O projeto atual utiliza os dados climáticos processados.
    df = pd.read_excel(cfg.CLIMA_PROCESSADOS)

    # Colunas climáticas utilizadas pelo modelo.
    col_irr = "irradiancia_W_m2"

    # Compatibilidade com as duas nomenclaturas que já apareceram
    # nos arquivos do projeto.
    if "temperatura" in df.columns:
        col_temp = "temperatura"
    elif "temperatura_C" in df.columns:
        col_temp = "temperatura_C"
    elif "temperatura_ambiente_C" in df.columns:
        col_temp = "temperatura_ambiente_C"
    else:
        raise KeyError(
            "O arquivo climático precisa conter uma coluna de temperatura "
            "('temperatura', 'temperatura_C' ou 'temperatura_ambiente_C')."
        )

    if col_irr not in df.columns:
        raise KeyError(
            f"O arquivo climático não possui a coluna '{col_irr}'."
        )

    irradiancia = pd.to_numeric(
        df[col_irr],
        errors="coerce"
    ).to_numpy(dtype=float)

    temperatura = pd.to_numeric(
        df[col_temp],
        errors="coerce"
    ).to_numpy(dtype=float)

    # Verificação básica dos dados de entrada.
    if len(irradiancia) != 8760:
        raise ValueError(
            f"Esperados 8760 pontos climáticos; encontrados "
            f"{len(irradiancia)}."
        )

    if np.isnan(irradiancia).any() or np.isnan(temperatura).any():
        raise ValueError(
            "Existem valores NaN nos dados climáticos utilizados pelo PVWatts."
        )

    pvshape = gera_pvshape(
        irradiancia,
        temperatura
    )

    pvshape = np.asarray(
        pvshape,
        dtype=float
    )

    if len(pvshape) != 8760:
        raise ValueError(
            f"O PVWatts retornou {len(pvshape)} pontos; "
            "esperados 8760."
        )

    # Segurança: PVShape representa potência AC normalizada.
    pvshape = np.clip(
        pvshape,
        0.0,
        1.0
    )

    arquivo = cfg.COM_PV / "PVShape.dss"

    with open(
        arquivo,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(
            "New LoadShape.PVShape "
            f"npts={len(pvshape)} "
            "interval=1 "
            "mult=("
            + ",".join(
                f"{valor:.6f}"
                for valor in pvshape
            )
            + ")\n"
        )

    print(
        f"PVShape PVWatts gerado: {arquivo}"
    )

    print(
        f"  Pontos       : {len(pvshape)}"
    )

    print(
        f"  Mínimo       : {pvshape.min():.6f}"
    )

    print(
        f"  Máximo       : {pvshape.max():.6f}"
    )

    return arquivo


# 5.2 - Verifica o número de fases do bus para a correta parametrização do PV
def extrai_num_fases(bus):

    partes = bus.split(".")

    if len(partes) == 1:
        return 3
    fases = [
        x
        for x in partes[1:]
        if x in ["1","2","3"]
    ]

    if len(fases) == 0:
        return 3

    return len(fases)

# 5.2 - Cria os arquivo .dss contendo a definição de todos os PVs do cenário de analisado.
# O PV é inserido na rede através do comando "New PVSystem" com seus respectivos parâmetros:
# nome, bus de conexão, número de fases, potência instalada e PVShape calculado pelo PVWatts.
def geradoresPVs_dss(
        cenario,
        resumo,
        penetracaoPV,
        volt_var=False
        ):
    """
    Gera o arquivo DSS do cenário.

    O cenário Volt-VAr usa exatamente os mesmos PVs, barramentos
    e potências do cenário original. A única diferença é a inclusão
    do XYCurve e do InvControl.
    """

    sufixo = "_VV" if volt_var else ""

    arquivo_dss = (
        cfg.COM_PV /
        f"geradoresPV_{int(100 * penetracaoPV)}{sufixo}.dss"
    )

    linhas = []

    # ----------------------------------------------------------
    # PVSystems
    # ----------------------------------------------------------

    for pv in cenario:

        fases = extrai_num_fases(
            pv["bus"]
        )

        linha = (
            f"New PVSystem.{pv['nome']} "
            f"bus1={pv['bus']} "
            f"phases={fases} "
            f"kV=0.208 "
            f"kVA={pv['potencia']:.3f} "
            f"Pmpp={pv['potencia']:.3f} "
            f"model=1 "
            f"conn=wye "
            f"pf=1 "
            f"irradiance=1 "
            f"temperature=25 "
            f"daily=PVShape"
        )

        linhas.append(linha)

    # ----------------------------------------------------------
    # Volt-VAr - IEEE 1547-2018 / Category B
    # ----------------------------------------------------------
    # Curva de referência adotada para o cenário Volt-VAr.
    #
    # X: tensão em pu
    # Y: potência reativa normalizada (pu de VARMAX)
    #
    # V = 0.92 pu -> Q = +0.44 pu
    # V = 0.98 pu -> Q =  0.00 pu
    # V = 1.02 pu -> Q =  0.00 pu
    # V = 1.08 pu -> Q = -0.44 pu
    #
    # A orientação do sinal foi previamente validada
    # experimentalmente na rede:
    #     Q > 0 -> elevação da tensão
    #     Q < 0 -> redução da tensão
    #
    # A curva é utilizada com RefReactivePower=VARMAX.
    #
    if volt_var:

        linhas.append("")

        linhas.append(
            "! Curva Volt-VAr de referência - IEEE 1547-2018 Category B"
        )

        linhas.append(
            "New XYCurve.VoltVarCurve "
            "npts=4 "
            "Xarray=[0.92 0.98 1.02 1.08] "
            "Yarray=[+0.44 0.00 0.00 -0.44]"  # IEEE --> "[+0.44 0.00 0.00 -0.44]"
        )

        linhas.append(
            "New InvControl.InvPVCtrl "
            "mode=VOLTVAR "
            "vvc_curve1=VoltVarCurve "
            "voltage_curvex_ref=rated "
            "RefReactivePower=VARMAX "
            "deltaQ_factor=1 "
            "VoltageChangeTolerance=0.01 "
            "VarChangeTolerance=0.01 "
            "EventLog=Yes"
        )


    with open(
            arquivo_dss,
            "w"
            ) as f:

        f.write(
            "\n".join(linhas)
        )

    # O XLSX representa a distribuição dos PVs, que é a mesma
    # para o cenário normal e para o Volt-VAr.
    if not volt_var:

        resumo.to_excel(
            cfg.COM_PV /
            f"geradoresPV_{int(100 * penetracaoPV)}.xlsx",
            index=False
        )

    print(
        f"\nGerado {arquivo_dss.name}."
    )


def gera_master_pv(
        nivelPV,
        volt_var=False
        ):

    sufixo = "_VV" if volt_var else ""

    arquivo = (
        cfg.COM_PV /
        f"PV_Master{int(100 * nivelPV)}{sufixo}.dss"
    )

    arquivo_pv = (
        cfg.COM_PV /
        f"geradoresPV_{int(100 * nivelPV)}{sufixo}.dss"
    )

    with open(
            arquivo,
            "w"
            ) as f:

        arquivo_pvshape = cfg.COM_PV / "PVShape.dss"

        f.write(
            f"Redirect {arquivo_pvshape}\n"
            f"Redirect {arquivo_pv}\n"
        )

    print(
        f"\nGerado {arquivo.name}."
    )


def plota_distribuicao(resumo, penetracao):
    
    resumo = resumo.sort_values("Carga_kW")
    
    x = np.arange(len(resumo))
    
    # Plot 1 - Load and PV by bus
    plt.figure(figsize=(12, 6))

    plt.bar(
        x,
        resumo["Carga_kW"],
        label="Load"
    )
    
    plt.bar(
        x,
        resumo["PV_kW"],
        label="PV"
    )
    
    plt.grid()
    plt.legend()
    plt.xlabel("Buses (sorted by load)")
    plt.ylabel("Power (kW)")
    plt.title(
        f"Load and PV distribution 60% penetration" #" ({100*penetracao:.0f}% penetration)"
    )
    
    plt.tight_layout()
    plt.show()
    plt.close()
    
    # Plot 2 - Load vs. PV scatter plot
    plt.figure(figsize=(8, 6))
    
    plt.scatter(
        resumo["Carga_kW"],
        resumo["PV_kW"],
        s=15
    )
    
    plt.grid()
    plt.xlabel("Load (kW)")
    plt.ylabel("Installed PV (kW)")
    plt.title(
        f"Installed PV power versus load 60% penetration" #" ({100*penetracao:.0f}% penetration)"
    )
    
    plt.tight_layout()
    plt.show()
    plt.close()


def plota_sistemas_pv(distribuicao, penetracao):

    potencias = [
        pv["potencia"]
        for pv in distribuicao
        ]
    
    plt.figure(figsize=(10,5))
    
    plt.hist(
        potencias,
        bins=np.arange(0, 11, 0.5),
        edgecolor="black"
        )
    
    plt.grid()
    plt.xlabel("Potência dos PVs (kW)")
    plt.ylabel("Quantidade de sistemas")
    plt.title(
        f"Distribuição das potências dos sistemas PV\n"
        f"Cenário com {penetracao:.2f} kW de FV"
    )
    
    plt.tight_layout()
    plt.show()
    plt.close()
     
# Função principal da Etapa 5
def gerar_dss(
        cenarios,
        nivelPV
        ):

    resumo_final = []

    for (
            penetracao,
            dados
            ), nivel in zip(
                cenarios.items(),
                nivelPV
            ):

        # ======================================================
        # CENÁRIO ORIGINAL - FP = 1
        # ======================================================

        geradoresPVs_dss(
            dados["distribuicao"],
            dados["resumo"],
            nivel,
            volt_var=False
        )

        gera_master_pv(
            nivel,
            volt_var=False
        )

        # ======================================================
        # CENÁRIO VOLT-VAR
        # ======================================================
        # Mesma distribuição de PVs; apenas acrescenta InvControl.
        # ======================================================

        geradoresPVs_dss(
            dados["distribuicao"],
            dados["resumo"],
            nivel,
            volt_var=True
        )

        gera_master_pv(
            nivel,
            volt_var=True
        )

        plota_distribuicao(
            dados["resumo"],
            nivel
        )

        resumo_final.append({

            "Penetracao":
                100 * nivel,

            "Potencia":
                dados["resumo"]["PV_kW"].sum(),

            "Numero_PVs":
                len(
                    dados["distribuicao"]
                )
        })

    resumo_final = pd.DataFrame(
        resumo_final
    )

    resumo_final.to_excel(
        cfg.LOG_CENARIOS,
        index=False
    )

    print("\n")
    print(
        resumo_final
    )

    plota_distribuicao(
        dados["resumo"],
        penetracao
    )

    plota_sistemas_pv(
        dados["distribuicao"],
        penetracao
    )


# Step 6 - Additional plots
# Plot baseline load (average daytime load) and PV penetration levels
def plota_baseload_nivelPV(curva, carga_media, potenciasPV, niveisPV):
    
    plt.figure(figsize=(10, 6))
    
    plt.plot(
        curva.index,
        curva.values,
        linewidth=3,
        color="black",
        label="Average load"
    )
    
    plt.axhline(
        carga_media,
        color="red",
        linestyle="--",
        label="Average daytime load without PV"
    )
    
    cores = [
        "green",
        "blue",
        "orange",
        "purple"
    ]
    
    for i, (potencia, nivel) in enumerate(zip(potenciasPV, niveisPV)):

        plt.axhline(
            potencia,
            color=cores[i],
            linestyle=":",
            linewidth=2,
            label=f"{100*nivel:.0f}% ({potencia:.0f} kW)"
        )
    
    plt.grid()
    plt.xlabel("Hour")
    plt.ylabel("Power (kW)")
    plt.title("Average Daytime Load and PV Penetration Levels")
    plt.legend()
    plt.tight_layout()
    plt.show()
#####################################################################
# PRINCIPAL
#####################################################################
def main():

    # Percentuais de penetração PV desejados
    percentual_de_PVs = [
        0.20,
        0.40,
        0.60
    ]

    # ----------------------------------------------------------
    # PARÂMETROS DA DISTRIBUIÇÃO
    # ----------------------------------------------------------
    # Limite máximo de PV por bus em relação à carga do bus.
    # Ex.: 0.40 = máximo 40% da carga local.
    # Este é o principal parâmetro a ser alterado nos testes.
    max_pv_por_bus = MAX_PV_PERCENT_LOAD_BUS

    # Estratégia recomendada para os testes com Volt-VAr:
    # distribuição balanceada, evitando concentração aleatória.
    estrategia_distribuicao = ESTRATEGIA_DISTRIBUICAO_PV

    print("\nParâmetros da distribuição dos PVs:")
    print(
        f"  Limite PV/carga por bus : "
        f"{100 * max_pv_por_bus:.1f}%"
    )
    print(
        f"  Estratégia               : "
        f"{estrategia_distribuicao}"
    )

    # Etapa 1 - Leitura do baseload e calculo da carga média diurna no barramento da
    # subestação.Leitura da curva de potência ativa do barramento da subestação, sem PV.
    carga_media, curva = calcula_media_diurna(
        cfg.RESULTADOS_BASE
    )
    
    # Etapa 2 - Determina a potência PV total (Potência alvo) a ser inserida;
    total_PV = calcula_potencia_PV_alvo(
        carga_media,
        percentual_de_PVs
    )
    
    salvar_potencias_cenarios(
        percentual_de_PVs,
        total_PV
    )

    # Etapa 3 - Leitura dos arquivos Loadshapes.dss para coletar dados dos
    # bus (identificador e carga)
    dados_cargas = buscar_dados_buses(
        [
            cfg.L_FEEDERA,
            cfg.L_FEEDERB,
            cfg.L_FEEDERC
        ]
    )

    # Etapa 4 - Realiza a inserção dos PVs
    cenarios = GERA_POPULACAO_PVs(
        dados_cargas,
        percentual_de_PVs,
        total_PV
    )

    # Etapa 5 - Construção dos arquivos .dss
    #
    # Primeiro gera o PVShape através do PVWatts.
    # Depois os arquivos dos cenários referenciam esse PVShape.
    gera_pvshape_pvwatts()

    gerar_dss(
        cenarios,
        percentual_de_PVs
    )

    # Etapa 6 - Plota curvas baseload (carga média diurna) e níveis PV 
    plota_baseload_nivelPV(
        curva,
        carga_media,
        total_PV,
        percentual_de_PVs
    )
    
    print("\nPROCESSAMENTO CONCLUÍDO")
    print(
        "\nArquitetura FV utilizada:"
        "\n  INMET → PVWatts → PVShape AC → OpenDSS"
        "\n  Tdaily/TempShape: NÃO utilizado"
    )

main()